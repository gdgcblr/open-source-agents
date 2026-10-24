// The three-stage render.
//
//   1. Synthesize every scene's narration and probe its duration, so pacing is
//      known before a single frame is recorded.
//   2. Drive the app through one continuous Playwright recording, noting the
//      wall-clock offset at which each scene begins. One take, no stitching —
//      which is why the output has no seams.
//   3. Mix the clips onto that video at their offsets and encode an MP4.

import { chromium } from 'playwright'
import { mkdirSync, rmSync, existsSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { synthesizeAll, ffprobeDur } from './tts.mjs'
import { setStage } from './overlay.mjs'
import { runSteps, sleep } from './steps.mjs'
import { padMs } from './timing.mjs'
import { mix } from './mix.mjs'
import { findChrome, launchArgs } from './preflight.mjs'

/** Remove a directory, tolerating a shell holding it open on Windows. */
function resetDir(dir) {
  try { if (existsSync(dir)) rmSync(dir, { recursive: true, force: true }) } catch { /* reused in place */ }
  mkdirSync(dir, { recursive: true })
}

/**
 * Render a demo video.
 * @param {object} cfg       normalised config
 * @param {object} [opts]
 * @param {boolean} [opts.dryRun]  skip TTS and encoding; just run the walkthrough
 * @param {string[]} [opts.only]   render only these scene ids
 * @returns {Promise<object>} a run report
 */
export async function render(cfg, { dryRun = false, only = null, log = console.log } = {}) {
  const scenes = only?.length ? cfg.scenes.filter(s => only.includes(s.id)) : cfg.scenes
  if (!scenes.length) throw new Error(`No scenes to render${only ? ` matching: ${only.join(', ')}` : ''}`)

  const outDir = cfg.output.dir
  const audioDir = path.join(outDir, 'audio')
  const videoDir = path.join(outDir, 'video')
  const finalFile = path.join(outDir, cfg.output.file)
  mkdirSync(outDir, { recursive: true })
  resetDir(videoDir)

  // ---- 1. voiceover -------------------------------------------------------
  let audio = { files: {}, seconds: {}, engineUsed: 'none' }
  if (dryRun) {
    log('\n[1/3] Skipping voiceover (--dry-run)')
    // Dry runs still need a per-scene hold, or every step races past its caption.
    for (const s of scenes) audio.seconds[s.id] = 0
  } else {
    log(`\n[1/3] Synthesizing narration (${cfg.voice.engine})...`)
    resetDir(audioDir)
    audio = synthesizeAll(scenes, cfg.voice, audioDir, log)
  }

  // ---- 2. record ----------------------------------------------------------
  log('\n[2/3] Recording the walkthrough...')
  const executablePath = findChrome(cfg.app.chromePath)
  const browser = await chromium.launch({
    ...(executablePath ? { executablePath } : {}),
    headless: cfg.app.headless !== false,
    args: launchArgs(),
  })
  const { width, height } = cfg.app.viewport
  const context = await browser.newContext({
    viewport: { width, height },
    colorScheme: cfg.app.colorScheme,
    recordVideo: dryRun ? undefined : { dir: videoDir, size: { width, height } },
  })
  const page = await context.newPage()

  const vars = {}
  const report = { scenes: [], config: path.join(cfg.configDir, ''), dryRun }
  const marks = []
  let rawVideo = null

  try {
    const recStart = Date.now()
    await page.goto(cfg.app.url, { waitUntil: 'commit' })
    if (cfg.app.waitForSelector) {
      await page.locator(cfg.app.waitForSelector).first().waitFor({ timeout: 30000 })
        .catch(() => log(`   (app.waitForSelector "${cfg.app.waitForSelector}" never appeared — continuing)`))
    }

    for (const scene of scenes) {
      const mark = Date.now() - recStart
      marks.push(mark)
      const narrSec = audio.seconds[scene.id] ?? 0
      log(` · ${scene.id}  @${(mark / 1000).toFixed(1)}s  (narration ${narrSec.toFixed(1)}s)`)

      // The overlay lives in the page, so a scene that navigated has to have it
      // put back. setStage is idempotent and cheap.
      await setStage(page, {
        mode: scene.layout, title: scene.title, subtitle: scene.subtitle, theme: cfg.theme,
      }).catch(e => log(`   (overlay failed: ${e.message})`))

      const t0 = Date.now()
      const steps = await runSteps(scene.steps, { page, vars, outDir, log })
      const pad = dryRun ? 0 : padMs(narrSec, Date.now() - t0, cfg.voice.tailMs)
      if (pad > 0) await sleep(pad)

      report.scenes.push({
        id: scene.id, atMs: mark, narrationSec: narrSec,
        stepsRun: steps.length, stepsFailed: steps.filter(s => !s.ok).length, steps,
      })
    }

    if (cfg.outro?.title && !dryRun) {
      await setStage(page, {
        mode: 'title', title: cfg.outro.title, subtitle: cfg.outro.subtitle, theme: cfg.theme,
      }).catch(() => {})
      await sleep(cfg.outro.holdMs || 3000)
    }
    await setStage(page, { mode: 'none', theme: cfg.theme }).catch(() => {})
    await sleep(500)

    const video = page.video()
    await context.close()
    rawVideo = video ? await video.path() : null
  } finally {
    await context.close().catch(() => {})
    await browser.close().catch(() => {})
  }

  const failed = report.scenes.reduce((n, s) => n + s.stepsFailed, 0)
  if (dryRun) {
    log(`\n[3/3] Skipping encode (--dry-run)`)
    log(`\nDry run complete: ${report.scenes.length} scene(s), ${failed} failed step(s).`)
    report.ok = failed === 0
    writeFileSync(path.join(outDir, 'dry-run.json'), JSON.stringify(report, null, 2))
    log(`Report: ${path.join(outDir, 'dry-run.json')}`)
    return report
  }

  // ---- 3. mix + encode ----------------------------------------------------
  if (!rawVideo) throw new Error('Playwright produced no video file')
  log(`\n[3/3] Mixing narration and encoding MP4...`)
  const videoDuration = ffprobeDur(rawVideo)
  try { if (existsSync(finalFile)) rmSync(finalFile, { force: true }) } catch {}
  mix({
    videoFile: rawVideo,
    audioFiles: scenes.map(s => audio.files[s.id]),
    marksMs: marks,
    videoDuration,
    outFile: finalFile,
    crf: cfg.output.crf,
    preset: cfg.output.preset,
  })

  report.ok = true
  report.file = finalFile
  report.durationSec = ffprobeDur(finalFile)
  report.failedSteps = failed
  log(`\n✅ ${finalFile}`)
  log(`   ${report.durationSec.toFixed(1)}s · ${width}x${height} · ${scenes.length} scenes · ${failed} skipped step(s)`)
  return report
}
