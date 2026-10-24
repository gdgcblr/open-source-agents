#!/usr/bin/env node
// autodemo CLI.
//
//   autodemo preflight [--config f]
//   autodemo render    [--config f] [--out dir] [--dry-run] [--scene id ...]
//   autodemo thumbnail [--config f] [--at 3]
//   autodemo init      [--dir .] [--url http://localhost:5173/]

import { existsSync, writeFileSync, mkdirSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { loadConfig } from '../src/engine/config.mjs'
import { preflight, printPreflight } from '../src/engine/preflight.mjs'
import { render } from '../src/engine/record.mjs'
import { makeThumbnail } from '../src/engine/thumbnail.mjs'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const PKG = JSON.parse(readFileSync(path.join(HERE, '..', 'package.json'), 'utf8'))

const USAGE = `
autodemo ${PKG.version} — narrated demo videos of any running web app

  autodemo preflight  [--config <file>]
      Check ffmpeg, ffprobe, a browser, the app URL and the TTS engine.

  autodemo render     [--config <file>] [--out <dir>] [--dry-run] [--scene <id>]...
      Render the video. --dry-run skips TTS and encoding and reports which
      steps succeeded — use it while you iterate on a scene file.

  autodemo thumbnail  [--config <file>] [--at <seconds>]
      Render a title-card thumbnail over a frame of the finished video.

  autodemo init       [--dir <dir>] [--url <url>]
      Scaffold a starter autodemo.config.yaml.

Default config: ./autodemo.config.yaml
`

function parseArgs(argv) {
  const out = { _: [], scene: [] }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a === '--dry-run') out.dryRun = true
    else if (a === '--help' || a === '-h') out.help = true
    else if (a === '--version' || a === '-v') out.version = true
    else if (a === '--scene') out.scene.push(argv[++i])
    else if (a === '--config' || a === '-c') out.config = argv[++i]
    else if (a === '--out') out.out = argv[++i]
    else if (a === '--url') out.url = argv[++i]
    else if (a === '--dir') out.dir = argv[++i]
    else if (a === '--at') out.at = Number(argv[++i])
    else out._.push(a)
  }
  return out
}

function resolveConfigPath(given) {
  if (given) return given
  for (const f of ['autodemo.config.yaml', 'autodemo.config.yml', 'autodemo.config.json']) {
    if (existsSync(f)) return f
  }
  return 'autodemo.config.yaml'
}

const STARTER = url => `# autodemo — https://github.com/gdgcblr/open-source-agents/tree/main/agents/autodemo
#
# Edit the narration, run \`autodemo render --dry-run\` until every step
# reports ✓, then run \`autodemo render\`.

app:
  url: ${url}
  viewport: { width: 1600, height: 900 }
  chromePath: auto
  # waitForSelector: "#root"      # readiness probe before scene 1

voice:
  engine: edge-tts                # edge-tts | sapi | none
  voice: en-US-AriaNeural
  rate: "+0%"
  tailMs: 750

theme:
  accent: "#7dd3fc"
  font: "Inter, Segoe UI, system-ui, sans-serif"
  position: bottom
  eyebrow: "My Product"

output:
  dir: ./autodemo-out
  file: demo.mp4
  crf: 20
  thumbnail: true

outro:
  title: "Try it yourself"
  subtitle: "example.com"
  holdMs: 3500

scenes:
  - id: intro
    layout: title
    title: "My App"
    subtitle: "What it does, in ninety seconds"
    narration: >-
      This is My App. It helps teams keep track of their work without the
      ceremony. Let me show you what it can do.
    steps: []

  - id: first_feature
    layout: caption
    title: "The dashboard"
    subtitle: "Everything in one view"
    narration: >-
      The dashboard is the first thing you see. It pulls together the work in
      flight, who owns it, and what is blocked, so nothing needs chasing.
    steps:
      - { do: click, role: button, name: "Dashboard" }
      - { do: wait, ms: 1500 }
      - { do: scrollPanel, selector: "main", to: bottom }
`

async function main() {
  const args = parseArgs(process.argv.slice(2))
  const cmd = args._[0]

  if (args.version) { console.log(PKG.version); return 0 }
  if (args.help || !cmd) { console.log(USAGE); return cmd ? 0 : 1 }

  if (cmd === 'init') {
    const dir = path.resolve(args.dir || '.')
    mkdirSync(dir, { recursive: true })
    const file = path.join(dir, 'autodemo.config.yaml')
    if (existsSync(file)) { console.error(`Refusing to overwrite ${file}`); return 1 }
    writeFileSync(file, STARTER(args.url || 'http://localhost:5173/'), 'utf8')
    console.log(`Created ${file}`)
    console.log('Next:  autodemo preflight  ->  autodemo render --dry-run  ->  autodemo render')
    return 0
  }

  const cfg = loadConfig(resolveConfigPath(args.config))
  if (args.out) cfg.output.dir = path.resolve(args.out)

  if (cmd === 'preflight') {
    const result = await preflight(cfg)
    return printPreflight(result) ? 1 : 0
  }

  if (cmd === 'render') {
    const result = await preflight(cfg)
    if (printPreflight(result)) return 1
    const report = await render(cfg, { dryRun: args.dryRun, only: args.scene })
    if (!args.dryRun && cfg.output.thumbnail) {
      const { jpg } = await makeThumbnail(cfg, { videoFile: report.file })
      console.log(`   thumbnail: ${jpg}`)
    }
    return report.ok ? 0 : 1
  }

  if (cmd === 'thumbnail') {
    const { png, jpg } = await makeThumbnail(cfg, { atSec: args.at ?? null })
    console.log(`${png}\n${jpg}`)
    return 0
  }

  console.error(`Unknown command "${cmd}".`)
  console.log(USAGE)
  return 1
}

main().then(
  code => process.exit(code),
  err => { console.error(`\n✗ ${err.message}\n`); process.exit(1) },
)
