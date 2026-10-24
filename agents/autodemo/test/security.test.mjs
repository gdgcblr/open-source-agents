// A config file is data: people copy them between projects and agents write
// them from things they read. These tests pin the places where that data
// reaches the filesystem or the process table.

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { writeFileSync, mkdtempSync, mkdirSync, existsSync, readdirSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { findChrome, launchArgs } from '../src/engine/preflight.mjs'
import { validateConfig } from '../src/engine/config.mjs'

function sandboxDir() {
  const d = mkdtempSync(path.join(tmpdir(), 'autodemo-sec-'))
  test.after?.(() => { try { rmSync(d, { recursive: true, force: true }) } catch {} })
  return d
}

const withEnv = (key, value, fn) => {
  const had = Object.prototype.hasOwnProperty.call(process.env, key)
  const old = process.env[key]
  if (value === null) delete process.env[key]; else process.env[key] = value
  try { return fn() } finally {
    if (had) process.env[key] = old; else delete process.env[key]
  }
}

test('a config cannot point chromePath at an arbitrary executable', () => {
  const dir = sandboxDir()
  const payload = path.join(dir, 'payload.exe')
  writeFileSync(payload, 'MZ')
  withEnv('CHROME_PATH', null, () => {
    assert.throws(() => findChrome(payload, { configDir: dir }),
      /Refusing to launch/)
  })
})

test('a config cannot carry its own browser binary next to itself', () => {
  // The realistic attack: a repo ships autodemo.config.yaml plus "chrome.exe".
  const dir = sandboxDir()
  const planted = path.join(dir, 'chrome.exe')
  writeFileSync(planted, 'MZ')
  withEnv('CHROME_PATH', null, () => {
    assert.throws(() => findChrome(planted, { configDir: dir }),
      /inside the config directory/)
  })
})

test('a browser outside the config directory is still allowed', () => {
  const browserDir = sandboxDir()
  const configDir = sandboxDir()
  const chrome = path.join(browserDir, 'chrome.exe')
  writeFileSync(chrome, 'MZ')
  withEnv('CHROME_PATH', null, () => {
    assert.equal(findChrome(chrome, { configDir }), chrome)
  })
})

test('CHROME_PATH is trusted — the person running the command typed it', () => {
  const dir = sandboxDir()
  const odd = path.join(dir, 'my-custom-build')
  writeFileSync(odd, 'MZ')
  withEnv('CHROME_PATH', odd, () => {
    assert.equal(findChrome('auto', { configDir: dir }), odd)
  })
})

test('a missing chromePath is reported rather than silently ignored', () => {
  withEnv('CHROME_PATH', null, () => {
    assert.throws(() => findChrome('/no/such/chrome.exe', {}), /does not exist/)
  })
})

test('output.file cannot escape the output directory', () => {
  const base = { app: { url: 'http://x.test/' }, scenes: [{ id: 'a' }] }
  for (const file of ['../../evil.mp4', 'sub/dir.mp4', '..\\evil.mp4', '/etc/passwd']) {
    const r = validateConfig({ ...base, output: { file } })
    assert.equal(r.valid, false, `output.file "${file}" should be rejected`)
  }
  assert.equal(validateConfig({ ...base, output: { file: 'demo.mp4' } }).valid, true)
})

test('a screenshot name cannot escape the output directory', () => {
  const cfg = name => ({
    app: { url: 'http://x.test/' },
    scenes: [{ id: 'a', steps: [{ do: 'screenshot', name }] }],
  })
  assert.equal(validateConfig(cfg('../../owned')).valid, false)
  assert.equal(validateConfig(cfg('ok-name')).valid, true)
})

test('--no-sandbox is opt-in, not always on', () => {
  if (process.platform !== 'linux') return   // the flag is only added on Linux
  withEnv('CI', null, () => withEnv('AUTODEMO_NO_SANDBOX', null, () => {
    assert.ok(!launchArgs().includes('--no-sandbox'))
  }))
  withEnv('CI', '1', () => {
    assert.ok(launchArgs().includes('--no-sandbox'))
  })
})

test('a previous run is cleared without recursively deleting anything', async () => {
  // resetDir must never rm -rf a user-supplied path. It removes only the
  // media it produces, and leaves everything else where it is.
  const { render } = await import('../src/engine/record.mjs')
  const dir = sandboxDir()
  const outDir = path.join(dir, 'out')
  mkdirSync(path.join(outDir, 'video'), { recursive: true })
  const precious = path.join(outDir, 'video', 'NOTES.txt')
  const stale = path.join(outDir, 'video', 'old.webm')
  writeFileSync(precious, 'do not delete me')
  writeFileSync(stale, 'stale recording')

  // Fail the render immediately — resetDir has already run by then.
  await render({
    app: { url: 'http://127.0.0.1:1/', viewport: { width: 320, height: 240 }, chromePath: '/no/such/chrome.exe' },
    voice: { engine: 'none' }, theme: {}, outro: {},
    output: { dir: outDir, file: 'x.mp4' },
    scenes: [{ id: 'a', layout: 'none', steps: [] }], configDir: dir,
  }, { log: () => {} }).catch(() => {})

  assert.ok(existsSync(precious), 'resetDir deleted a file it did not create')
  assert.ok(!existsSync(stale), 'resetDir left a stale recording behind')
  assert.ok(readdirSync(outDir).includes('video'))
})
