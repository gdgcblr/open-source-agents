#!/usr/bin/env node
// An MCP server over the autodemo engine, so agent frameworks that are not
// Claude Code can drive it too.
//
//   autodemo_preflight     — check the environment and the app URL
//   autodemo_describe_app  — open the app and return its accessibility tree,
//                            which is what you write a scene file from
//   autodemo_dry_run       — run the walkthrough, report per-step results
//   autodemo_render        — render the MP4
//
// Run:  node src/mcp/server.mjs      (stdio transport)

import { Server } from '@modelcontextprotocol/sdk/server/index.js'
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js'
import { CallToolRequestSchema, ListToolsRequestSchema } from '@modelcontextprotocol/sdk/types.js'
import { chromium } from 'playwright'
import { loadConfig } from '../engine/config.mjs'
import { preflight } from '../engine/preflight.mjs'
import { render } from '../engine/record.mjs'
import { makeThumbnail } from '../engine/thumbnail.mjs'
import { findChrome, launchArgs } from '../engine/preflight.mjs'

const CONFIG_ARG = {
  type: 'string',
  description: 'Path to an autodemo config (.yaml or .json). Defaults to ./autodemo.config.yaml',
}

const TOOLS = [
  {
    name: 'autodemo_preflight',
    description: 'Check that everything a render needs is present: ffmpeg, ffprobe, a browser, the app URL, and a TTS engine. Run this before anything else; it is cheap and it fails fast.',
    inputSchema: { type: 'object', properties: { config: CONFIG_ARG } },
  },
  {
    name: 'autodemo_describe_app',
    description: 'Open a URL in a browser and return its accessibility tree plus the page title. Use this to discover the real roles and accessible names to target in a scene file, instead of guessing selectors.',
    inputSchema: {
      type: 'object',
      required: ['url'],
      properties: {
        url: { type: 'string', description: 'The running app to open' },
        waitForSelector: { type: 'string', description: 'Readiness probe before snapshotting' },
        waitMs: { type: 'number', description: 'Extra settle time after load (default 2500)' },
      },
    },
  },
  {
    name: 'autodemo_dry_run',
    description: 'Run the whole walkthrough with no narration and no encoding, and report whether each step succeeded. Use it to iterate on a scene file before spending a full render.',
    inputSchema: {
      type: 'object',
      properties: {
        config: CONFIG_ARG,
        scenes: { type: 'array', items: { type: 'string' }, description: 'Only these scene ids' },
      },
    },
  },
  {
    name: 'autodemo_render',
    description: 'Render the narrated MP4. This takes real wall-clock time — roughly the length of the finished video plus encoding. Show the narration to the user and get approval before calling it.',
    inputSchema: {
      type: 'object',
      properties: {
        config: CONFIG_ARG,
        out: { type: 'string', description: 'Override output.dir' },
        thumbnail: { type: 'boolean', description: 'Also render a thumbnail' },
      },
    },
  },
]

const text = s => ({ content: [{ type: 'text', text: typeof s === 'string' ? s : JSON.stringify(s, null, 2) }] })
const fail = msg => ({ content: [{ type: 'text', text: msg }], isError: true })

// `describe_app` takes a URL from whatever is driving this server, which may
// be an agent acting on text it read somewhere. A browser will happily open
// file:// and data: URLs, and the accessibility tree would then hand back the
// contents of a local file. Only real web requests are allowed here.
function assertWebUrl(url) {
  let parsed
  try { parsed = new URL(url) } catch { throw new Error(`Not a valid URL: ${url}`) }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw new Error(`Only http and https URLs can be described, not ${parsed.protocol}`)
  }
  return parsed.href
}

async function describeApp({ url, waitForSelector, waitMs = 2500 }) {
  url = assertWebUrl(url)
  const executablePath = findChrome('auto')
  const browser = await chromium.launch({
    ...(executablePath ? { executablePath } : {}), headless: true, args: launchArgs(),
  })
  try {
    const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 })
    if (waitForSelector) {
      await page.locator(waitForSelector).first().waitFor({ timeout: 30000 }).catch(() => {})
    }
    await page.waitForTimeout(waitMs)
    return {
      url: page.url(),
      title: await page.title(),
      // The accessibility tree is the right thing to script from: it is what
      // getByRole matches against.
      accessibility: await page.accessibility.snapshot({ interestingOnly: true }),
    }
  } finally {
    await browser.close().catch(() => {})
  }
}

const server = new Server(
  { name: 'autodemo', version: '0.1.0' },
  { capabilities: { tools: {} } },
)

server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS }))

server.setRequestHandler(CallToolRequestSchema, async req => {
  const { name, arguments: args = {} } = req.params
  const cfgPath = args.config || 'autodemo.config.yaml'

  try {
    if (name === 'autodemo_describe_app') {
      return text(await describeApp(args))
    }

    if (name === 'autodemo_preflight') {
      const cfg = loadConfig(cfgPath)
      const { checks, fatal } = await preflight(cfg)
      return text({ ok: !fatal, checks })
    }

    if (name === 'autodemo_dry_run') {
      const cfg = loadConfig(cfgPath)
      const lines = []
      const report = await render(cfg, { dryRun: true, only: args.scenes, log: l => lines.push(l) })
      return text({
        ok: report.ok,
        scenes: report.scenes.map(s => ({
          id: s.id, stepsRun: s.stepsRun, stepsFailed: s.stepsFailed,
          failures: s.steps.filter(x => !x.ok).map(x => ({ step: x.step, error: x.error })),
        })),
        log: lines.join('\n'),
      })
    }

    if (name === 'autodemo_render') {
      const cfg = loadConfig(cfgPath)
      if (args.out) cfg.output.dir = args.out
      const { fatal, checks } = await preflight(cfg)
      if (fatal) return fail('Preflight failed:\n' + checks.filter(c => !c.ok)
        .map(c => `  ✗ ${c.name}: ${c.detail}${c.fix ? ` — fix: ${c.fix}` : ''}`).join('\n'))

      const lines = []
      const report = await render(cfg, { log: l => lines.push(l) })
      const out = {
        ok: report.ok, file: report.file,
        durationSec: report.durationSec,
        scenes: report.scenes.length,
        skippedSteps: report.failedSteps,
        log: lines.join('\n'),
      }
      if (args.thumbnail ?? cfg.output.thumbnail) {
        out.thumbnail = (await makeThumbnail(cfg, { videoFile: report.file })).jpg
      }
      return text(out)
    }

    return fail(`Unknown tool: ${name}`)
  } catch (e) {
    return fail(`${name} failed: ${e.message}`)
  }
})

await server.connect(new StdioServerTransport())
