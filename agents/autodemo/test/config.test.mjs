import { test } from 'node:test'
import assert from 'node:assert/strict'
import { validateConfig, normaliseConfig } from '../src/engine/config.mjs'

const good = {
  app: { url: 'http://localhost:5173/', viewport: { width: 1280, height: 720 } },
  voice: { engine: 'none' },
  scenes: [
    { id: 'intro', layout: 'title', title: 'X', narration: 'Hello.', steps: [] },
    {
      id: 'tour', layout: 'caption', narration: 'A tour.', steps: [
        { do: 'click', role: 'button', name: 'Dashboard' },
        { do: 'wait', ms: 1000 },
        { do: 'waitForText', text: 'Revenue', timeout: 15000 },
        { do: 'drag', button: 'right', path: [[0, -120], [-160, 0]], stepMs: 50 },
        { do: 'probeClick', pattern: 'W[MD]-K[0-9.]+', panel: 'aside', saveAs: 'pipe' },
      ],
    },
  ],
}

const ok = cfg => validateConfig(cfg).valid
const errs = cfg => validateConfig(cfg).errors.join(' | ')

test('a realistic config validates', () => {
  const r = validateConfig(good)
  assert.equal(r.valid, true, r.errors.join('\n'))
})

test('app.url is required', () => {
  const bad = { app: {}, scenes: [{ id: 'a' }] }
  assert.equal(ok(bad), false)
  assert.match(errs(bad), /url/)
})

test('at least one scene is required', () => {
  assert.equal(ok({ app: { url: 'http://x.test/' }, scenes: [] }), false)
})

test('an unknown step type is rejected', () => {
  const bad = { app: { url: 'http://x.test/' }, scenes: [{ id: 'a', steps: [{ do: 'teleport' }] }] }
  assert.equal(ok(bad), false)
  assert.match(errs(bad), /do/)
})

test('a misspelled top-level key is rejected rather than silently ignored', () => {
  const bad = { app: { url: 'http://x.test/' }, scenes: [{ id: 'a' }], voise: { engine: 'none' } }
  assert.equal(ok(bad), false)
})

test('a step missing its required field is rejected', () => {
  const bad = { app: { url: 'http://x.test/' }, scenes: [{ id: 'a', steps: [{ do: 'wait' }] }] }
  assert.equal(ok(bad), false)
  assert.match(errs(bad), /ms/)
})

test('a click needs something to click', () => {
  const noTarget = { app: { url: 'http://x.test/' }, scenes: [{ id: 'a', steps: [{ do: 'click' }] }] }
  assert.equal(ok(noTarget), false)
  const bySelector = { app: { url: 'http://x.test/' }, scenes: [{ id: 'a', steps: [{ do: 'click', selector: '#go' }] }] }
  assert.equal(ok(bySelector), true, errs(bySelector))
})

test('an unknown voice engine is rejected', () => {
  const bad = { app: { url: 'http://x.test/' }, voice: { engine: 'festival' }, scenes: [{ id: 'a' }] }
  assert.equal(ok(bad), false)
})

test('duplicate scene ids are rejected — they key the audio files', () => {
  const bad = { app: { url: 'http://x.test/' }, scenes: [{ id: 'a' }, { id: 'a' }] }
  assert.equal(ok(bad), false)
  assert.match(errs(bad), /duplicate scene id "a"/)
})

test('defaults fill in everything the user left out', () => {
  const cfg = normaliseConfig({ app: { url: 'http://x.test/' }, scenes: [{ id: 'a' }] },
    { configDir: process.cwd() })
  assert.equal(cfg.app.viewport.width, 1600)
  assert.equal(cfg.voice.engine, 'edge-tts')
  assert.equal(cfg.voice.tailMs, 750)
  assert.equal(cfg.output.file, 'demo.mp4')
  assert.equal(cfg.theme.position, 'bottom')
})

test('user values win over defaults, including nested ones', () => {
  const cfg = normaliseConfig({
    app: { url: 'http://x.test/', viewport: { width: 1920 } },
    voice: { engine: 'none' },
    scenes: [{ id: 'a' }],
  }, { configDir: process.cwd() })
  assert.equal(cfg.app.viewport.width, 1920)
  assert.equal(cfg.app.viewport.height, 900)   // the untouched half of the pair survives
  assert.equal(cfg.voice.engine, 'none')
  assert.equal(cfg.voice.rate, '+0%')
})

test('a scene with narration defaults to a caption, one without to no overlay', () => {
  const cfg = normaliseConfig({
    app: { url: 'http://x.test/' },
    scenes: [{ id: 'a', narration: 'hi' }, { id: 'b' }, { id: 'c', layout: 'title', title: 'T' }],
  }, { configDir: process.cwd() })
  assert.equal(cfg.scenes[0].layout, 'caption')
  assert.equal(cfg.scenes[1].layout, 'none')
  assert.equal(cfg.scenes[2].layout, 'title')
})

test('a relative output dir resolves against the config file, not the shell cwd', () => {
  const cfg = normaliseConfig({
    app: { url: 'http://x.test/' }, output: { dir: './out' }, scenes: [{ id: 'a' }],
  }, { configDir: '/projects/myapp/demo' })
  assert.match(cfg.output.dir.replace(/\\/g, '/'), /\/projects\/myapp\/demo\/out$/)
})
