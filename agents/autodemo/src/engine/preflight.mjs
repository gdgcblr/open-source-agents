// Preflight: check everything a render needs *before* spending ten minutes
// discovering that ffprobe is not on PATH. Every failed check carries the
// command that fixes it on this platform.

import { execFileSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'
import { hasEdgeTts } from './tts.mjs'

const IS_WIN = process.platform === 'win32'
const IS_MAC = process.platform === 'darwin'

/** Candidate Chrome/Edge locations, per platform. */
export function chromeCandidates() {
  if (IS_WIN) return [
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    `${process.env.LOCALAPPDATA || ''}/Google/Chrome/Application/chrome.exe`,
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  ]
  if (IS_MAC) return [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
  ]
  return [
    '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable',
    '/usr/bin/chromium', '/usr/bin/chromium-browser', '/snap/bin/chromium',
  ]
}

// A config file looks like data, and people copy them between projects. But
// `chromePath` names an executable that we then launch, so a hostile config
// shipped alongside a payload would be native code execution on the host.
// These two rules block the realistic version of that without taking the
// option away: the binary has to look like a browser, and it cannot live
// inside the config's own directory tree (where a payload would travel).
//
// CHROME_PATH is exempt — it was typed by whoever ran the command.
const BROWSER_NAME = /^(google-)?chrome(-stable|-beta|-dev|-headless-shell)?(\.exe)?$|^chromium(-browser)?(\.exe)?$|^msedge(\.exe)?$|^(Google Chrome|Chromium|Microsoft Edge)$/i

function assertLaunchable(file, configDir) {
  if (!existsSync(file)) throw new Error(`chromePath does not exist: ${file}`)
  if (!BROWSER_NAME.test(path.basename(file))) {
    throw new Error(
      `Refusing to launch "${path.basename(file)}" as a browser.\n` +
      `  app.chromePath must name a Chrome, Chromium or Edge binary.\n` +
      `  If this really is one, set CHROME_PATH in your environment instead.`)
  }
  if (configDir) {
    const rel = path.relative(path.resolve(configDir), path.resolve(file))
    if (rel && !rel.startsWith('..') && !path.isAbsolute(rel)) {
      throw new Error(
        `Refusing to launch a browser from inside the config directory: ${file}\n` +
        `  A config should not carry its own executable. Use an installed\n` +
        `  browser, set CHROME_PATH, or use chromePath: auto.`)
    }
  }
}

/**
 * Find a browser executable.
 * `null` is a success, not a failure: it means "use Playwright's bundled
 * chromium", which is what CI does.
 */
export function findChrome(configured = 'auto', { configDir = null } = {}) {
  if (process.env.CHROME_PATH) {
    if (!existsSync(process.env.CHROME_PATH)) {
      throw new Error(`CHROME_PATH does not exist: ${process.env.CHROME_PATH}`)
    }
    return process.env.CHROME_PATH
  }
  if (configured && configured !== 'auto') {
    assertLaunchable(configured, configDir)
    return configured
  }
  return chromeCandidates().find(p => p && existsSync(p)) || null
}

/** GPU flags that actually help on this platform (ANGLE/d3d11 is Windows-only). */
export function launchArgs() {
  const common = ['--hide-scrollbars', '--mute-audio', '--force-device-scale-factor=1']
  if (IS_WIN) return ['--use-angle=d3d11', '--enable-gpu', '--ignore-gpu-blocklist', ...common]
  if (IS_MAC) return ['--use-angle=metal', '--enable-gpu', ...common]
  // Linux/CI: software GL is the only thing reliably present on a headless
  // runner. --no-sandbox is gated: it is needed to run as root in a container,
  // but it drops a real protection layer, so it is opt-in rather than always on.
  const sandbox = process.env.CI || process.env.AUTODEMO_NO_SANDBOX ? ['--no-sandbox'] : []
  return ['--use-gl=angle', '--use-angle=swiftshader', ...sandbox, ...common]
}

function binOk(bin) {
  try { execFileSync(bin, ['-version'], { stdio: 'pipe' }); return true } catch { return false }
}

async function urlOk(url, timeoutMs = 8000) {
  const ctl = AbortSignal.timeout(timeoutMs)
  try {
    const r = await fetch(url, { signal: ctl, redirect: 'follow' })
    return { ok: r.ok || r.status < 500, status: r.status }
  } catch (e) {
    return { ok: false, status: String(e.message || e).split('\n')[0] }
  }
}

const INSTALL = {
  ffmpeg: IS_WIN ? 'winget install Gyan.FFmpeg'
    : IS_MAC ? 'brew install ffmpeg'
    : 'sudo apt-get install -y ffmpeg',
  edge: 'pip install -U edge-tts',
  chromium: 'npx playwright install chromium',
}

/**
 * Run every check.
 * @returns {{checks: Array<{name,ok,detail,fix?}>, fatal: boolean}}
 */
export async function preflight(cfg) {
  const checks = []
  const add = (name, ok, detail, fix) => checks.push({ name, ok, detail, fix })

  add('ffmpeg', binOk('ffmpeg'), binOk('ffmpeg') ? 'on PATH' : 'not found', INSTALL.ffmpeg)
  add('ffprobe', binOk('ffprobe'), binOk('ffprobe') ? 'on PATH' : 'not found', INSTALL.ffmpeg)

  let chrome = null, chromeErr = null
  try { chrome = findChrome(cfg.app.chromePath) } catch (e) { chromeErr = e.message }
  add('browser', !chromeErr,
    chromeErr || (chrome ? chrome : "system Chrome not found — using Playwright's bundled chromium"),
    INSTALL.chromium)

  const reach = await urlOk(cfg.app.url)
  add('app URL', reach.ok, `${cfg.app.url} -> ${reach.status}`,
    'start your dev server first, then re-run')

  const engine = cfg.voice.engine
  if (engine === 'none') {
    add('voice', true, 'engine: none — silent clips sized to the narration text')
  } else if (engine === 'edge-tts') {
    const py = hasEdgeTts()
    add('voice', true,
      py ? `edge-tts via ${py} (voice ${cfg.voice.voice})`
         : IS_WIN ? 'edge-tts missing — will fall back to Windows SAPI'
                  : 'edge-tts missing — will fall back to silent clips',
      py ? undefined : INSTALL.edge)
  } else {
    add('voice', IS_WIN, IS_WIN ? 'Windows SAPI' : 'sapi requested but this is not Windows',
      "set voice.engine to 'edge-tts' or 'none'")
  }

  add('scenes', cfg.scenes.length > 0,
    `${cfg.scenes.length} scene(s), ${cfg.scenes.reduce((n, s) => n + (s.steps?.length || 0), 0)} step(s)`)

  // Only the things a render genuinely cannot proceed without.
  const fatal = checks.some(c => !c.ok && ['ffmpeg', 'ffprobe', 'app URL', 'browser', 'scenes'].includes(c.name))
  return { checks, fatal }
}

/** Print the ✓/✗ checklist. Returns `fatal`. */
export function printPreflight({ checks, fatal }, log = console.log) {
  log('')
  for (const c of checks) {
    log(`  ${c.ok ? '✓' : '✗'} ${c.name.padEnd(10)} ${c.detail}`)
    if (!c.ok && c.fix) log(`      fix: ${c.fix}`)
  }
  log('')
  log(fatal ? '  Preflight failed — fix the ✗ items above.' : '  Preflight passed.')
  return fatal
}
