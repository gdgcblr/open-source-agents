// End-to-end: serve the bundled example app, render a short three-scene
// video with voice.engine: none, and assert the MP4 is real.
//
// This is the test that would have caught every bug worth catching in this
// project: a malformed filter string, a mark in the wrong order, a video with
// no audio track. It needs ffmpeg, ffprobe and a chromium on the machine, so
// it skips itself rather than failing when they are missing.

import { test, before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { execFileSync } from 'node:child_process'
import { readFileSync, existsSync, rmSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { normaliseConfig } from '../src/engine/config.mjs'
import { render } from '../src/engine/record.mjs'
import { ffprobeDur } from '../src/engine/tts.mjs'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const APP = path.join(HERE, '..', 'examples', 'todo-app', 'index.html')

function have(bin) {
  try { execFileSync(bin, ['-version'], { stdio: 'pipe' }); return true } catch { return false }
}
const SKIP = !have('ffmpeg') || !have('ffprobe')
  ? 'ffmpeg/ffprobe not on PATH' : false

let server, port, outDir

before(async () => {
  if (SKIP) return
  const html = readFileSync(APP)
  server = createServer((_, res) => { res.writeHead(200, { 'Content-Type': 'text/html' }); res.end(html) })
  await new Promise(r => server.listen(0, '127.0.0.1', r))
  port = server.address().port
  outDir = mkdtempSync(path.join(tmpdir(), 'autodemo-it-'))
})

after(() => {
  server?.close()
  if (outDir) { try { rmSync(outDir, { recursive: true, force: true }) } catch {} }
})

test('renders a three-scene narrated MP4 end to end', { skip: SKIP, timeout: 300000 }, async () => {
  const cfg = normaliseConfig({
    app: { url: `http://127.0.0.1:${port}/`, viewport: { width: 800, height: 600 }, waitForSelector: '#root' },
    voice: { engine: 'none', tailMs: 300 },
    output: { dir: outDir, file: 'it.mp4', crf: 30, preset: 'ultrafast' },
    scenes: [
      { id: 'one', layout: 'title', title: 'Taskbench', subtitle: 'Test render', narration: 'A short opening line for the test render.' },
      { id: 'two', layout: 'caption', title: 'Tasks', narration: 'The second scene adds a task and waits a moment.',
        steps: [{ do: 'click', selector: '#new-task' }, { do: 'type', text: 'hi', delay: 10 }, { do: 'press', key: 'Enter' }] },
      { id: 'three', layout: 'caption', title: 'Reports', narration: 'The third scene opens the reports tab.',
        steps: [{ do: 'navClick', name: 'Reports' }, { do: 'waitForText', text: 'Total shipped this month' }] },
    ],
  }, { configDir: outDir })

  const report = await render(cfg, { log: () => {} })

  assert.equal(report.ok, true)
  assert.ok(existsSync(report.file), `no MP4 at ${report.file}`)
  assert.equal(report.failedSteps, 0, 'some steps were skipped')

  // One video stream and one audio stream — a mix that silently dropped the
  // audio graph would still produce a playable file, so check explicitly.
  const probe = execFileSync('ffprobe', ['-v', 'error', '-show_entries',
    'stream=codec_type,codec_name', '-of', 'json', report.file], { encoding: 'utf8' })
  const streams = JSON.parse(probe).streams
  assert.equal(streams.filter(s => s.codec_type === 'video').length, 1)
  assert.equal(streams.filter(s => s.codec_type === 'audio').length, 1)
  assert.equal(streams.find(s => s.codec_type === 'video').codec_name, 'h264')
  assert.equal(streams.find(s => s.codec_type === 'audio').codec_name, 'aac')

  // Expected length: the three narration clips plus one tail each. Recording
  // start-up and the step time inside each scene add a little, so allow a
  // generous lower bound and a ceiling that would catch a runaway hold.
  const dur = ffprobeDur(report.file)
  assert.ok(dur > 6, `video is only ${dur}s — the scenes did not hold for their narration`)
  assert.ok(dur < 60, `video ran to ${dur}s — something waited far longer than it should`)

  // Marks must be strictly increasing: the ffmpeg filter delays each clip from
  // zero, so an out-of-order mark silently overlaps two scenes' narration.
  const marks = report.scenes.map(s => s.atMs)
  for (let i = 1; i < marks.length; i++) {
    assert.ok(marks[i] > marks[i - 1], `scene ${i} starts at ${marks[i]}ms, before scene ${i - 1}`)
  }
})

test('a dry run reports per-step results without encoding anything', { skip: SKIP, timeout: 180000 }, async () => {
  const cfg = normaliseConfig({
    app: { url: `http://127.0.0.1:${port}/`, viewport: { width: 800, height: 600 } },
    voice: { engine: 'none' },
    output: { dir: outDir, file: 'dry.mp4' },
    scenes: [
      { id: 'ok', narration: 'x', steps: [{ do: 'navClick', name: 'Reports' }] },
      { id: 'broken', narration: 'x', steps: [{ do: 'click', name: 'No Such Button', timeout: 1000 }] },
    ],
  }, { configDir: outDir })

  const report = await render(cfg, { dryRun: true, log: () => {} })

  assert.equal(report.dryRun, true)
  assert.equal(report.ok, false, 'a scene with a failing step should not report ok')
  assert.equal(report.scenes[0].stepsFailed, 0)
  assert.equal(report.scenes[1].stepsFailed, 1)
  assert.match(report.scenes[1].steps[0].step, /No Such Button/)
  assert.ok(!existsSync(path.join(outDir, 'dry.mp4')), 'a dry run must not encode a video')
})
