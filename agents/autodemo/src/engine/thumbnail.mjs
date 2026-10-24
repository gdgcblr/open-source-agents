// Optional thumbnail: grab a frame from the finished video, lay the title
// card over it, and screenshot that. Using a real frame as the backdrop means
// the thumbnail always looks like the video it belongs to.

import { execFileSync } from 'node:child_process'
import { chromium } from 'playwright'
import { readFileSync, existsSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { findChrome, launchArgs } from './preflight.mjs'
import { ffprobeDur } from './tts.mjs'

/** Pull a single frame from `video` at `atSec` into a PNG. */
export function grabFrame(video, atSec, outFile) {
  execFileSync('ffmpeg', ['-y', '-ss', String(atSec), '-i', video, '-frames:v', '1', outFile],
    { stdio: 'pipe' })
  return outFile
}

function cardHtml({ title, subtitle, eyebrow, accent, font, bgDataUri, width, height }) {
  return `<!doctype html><html><head><meta charset="utf-8"><style>
  html,body{margin:0;padding:0;width:${width}px;height:${height}px;overflow:hidden}
  body{font-family:${font};background:#030712}
  .bg{position:absolute;inset:0;background:url('${bgDataUri}') center/cover no-repeat;filter:saturate(1.1)}
  .scrim{position:absolute;inset:0;background:radial-gradient(ellipse at 30% 50%,rgba(3,7,18,.78),rgba(3,7,18,.95))}
  .wrap{position:absolute;inset:0;display:flex;flex-direction:column;justify-content:center;gap:22px;padding:0 9%}
  .eyebrow{font-size:20px;letter-spacing:6px;text-transform:uppercase;color:${accent};font-weight:600}
  .title{font-size:84px;line-height:1.05;font-weight:800;color:#fff;max-width:85%}
  .sub{font-size:30px;color:#cbd5e1;max-width:72%}
  .rule{width:120px;height:6px;border-radius:3px;background:${accent}}
  </style></head><body>
  <div class="bg"></div><div class="scrim"></div>
  <div class="wrap">
    <div class="eyebrow">${eyebrow || ''}</div>
    <div class="rule"></div>
    <div class="title">${title || ''}</div>
    <div class="sub">${subtitle || ''}</div>
  </div></body></html>`
}

/**
 * Render `thumbnail.png` / `thumbnail.jpg` next to the video.
 * @returns {Promise<{png: string, jpg: string}>}
 */
export async function makeThumbnail(cfg, { videoFile, atSec = null } = {}) {
  const outDir = cfg.output.dir
  const video = videoFile || path.join(outDir, cfg.output.file)
  if (!existsSync(video)) throw new Error(`No video to thumbnail: ${video}\nRun \`autodemo render\` first.`)

  const { width, height } = cfg.app.viewport
  const framePng = path.join(outDir, 'thumb_frame.png')
  // Default a quarter of the way in: far enough past the opening title card
  // that the backdrop is the app itself, not the card we are about to draw
  // over it again.
  const grabAt = atSec ?? Math.max(4, ffprobeDur(video) * 0.25)
  grabFrame(video, grabAt, framePng)
  const bgDataUri = 'data:image/png;base64,' + readFileSync(framePng).toString('base64')

  const first = cfg.scenes[0] || {}
  const html = cardHtml({
    title: first.title || 'Demo',
    subtitle: first.subtitle || '',
    eyebrow: cfg.theme.eyebrow,
    accent: cfg.theme.accent,
    font: cfg.theme.font,
    bgDataUri, width, height,
  })
  const htmlFile = path.join(outDir, 'thumbnail.html')
  writeFileSync(htmlFile, html, 'utf8')

  const executablePath = findChrome(cfg.app.chromePath)
  const browser = await chromium.launch({
    ...(executablePath ? { executablePath } : {}),
    headless: true, args: launchArgs(),
  })
  try {
    const page = await browser.newPage({ viewport: { width, height } })
    await page.goto('file://' + htmlFile.replace(/\\/g, '/'), { waitUntil: 'load' })
    const png = path.join(outDir, 'thumbnail.png')
    const jpg = path.join(outDir, 'thumbnail.jpg')
    await page.screenshot({ path: png })
    await page.screenshot({ path: jpg, type: 'jpeg', quality: 88 })
    return { png, jpg }
  } finally {
    await browser.close().catch(() => {})
  }
}
