// The step dispatcher: the declarative action vocabulary.
//
// Fault tolerance is the design rule here. Each step is attempted in
// isolation; a failure is logged as `(skipped: ...)` and the walkthrough
// carries on. A button that got renamed must never kill a five-minute render
// twelve scenes in — you want the video, with one dull moment in it, plus a
// log line telling you exactly which step to fix.
//
// Steps receive a context object rather than a bare page so that `probeClick`
// can stash what it found in run-scoped `vars`, and a later scene can refer
// back to it.

import path from 'node:path'

export const sleep = ms => new Promise(r => setTimeout(r, ms))

const DEFAULT_TIMEOUT = 15000

/** Resolve a Playwright locator from the common {role,name,selector,text} shape. */
function resolve(page, step) {
  const { role, name, exact = false, selector, text, within } = step
  const scope = within ? page.locator(within) : page
  if (selector) return scope.locator(selector).first()
  if (role && name) return scope.getByRole(role, { name, exact }).first()
  if (name) return scope.getByRole('button', { name, exact }).first()
  if (text) return scope.getByText(text, { exact }).first()
  throw new Error('step needs one of: selector, {role,name}, name, text')
}

/**
 * Click outward in an expanding spiral from the centre of the viewport (or of
 * `region`) until `panel`'s text matches `pattern`. This is what makes a
 * canvas or map app demoable at all: its features have no DOM nodes to
 * target, so the only way to "select a pipe" is to click until an inspector
 * panel says you hit one.
 *
 * Returns the first capture group (or the whole match) and stores it in
 * `vars[saveAs]`, so a later scene can exclude it and pick a different one.
 */
async function probeClick(step, ctx) {
  const { page, vars, log } = ctx
  const {
    pattern, panel, saveAs,
    spiral = {},
    excludeMatch, region, settleMs = 220,
  } = step
  const { steps: nSteps = 160, radiusStep = 2.5, angleStep = 0.7 } = spiral

  const re = new RegExp(pattern)
  const exclude = excludeMatch ? (vars[excludeMatch] ?? excludeMatch) : null
  const panelLoc = page.locator(panel)

  const box = region
    ? await page.locator(region).boundingBox()
    : { x: 0, y: 0, ...page.viewportSize() }
  if (!box) throw new Error(`probeClick: region ${region} has no bounding box`)

  const cx = box.x + box.width * 0.5
  const cy = box.y + box.height * 0.5
  for (let k = 0; k < nSteps; k++) {
    const angle = k * angleStep
    const radius = 4 + k * radiusStep
    const x = cx + radius * Math.cos(angle)
    const y = cy + radius * Math.sin(angle)
    if (x < box.x + 8 || x > box.x + box.width - 8) continue
    if (y < box.y + 8 || y > box.y + box.height - 8) continue
    await page.mouse.click(x, y)
    await sleep(settleMs)
    const txt = await panelLoc.evaluate(el => el.textContent).catch(() => '')
    const m = String(txt || '').match(re)
    if (m) {
      const hit = m[1] ?? m[0]
      if (exclude && hit === exclude) continue
      if (saveAs) vars[saveAs] = hit
      log?.(`     probeClick hit "${hit}" after ${k + 1} probes`)
      return hit
    }
  }
  throw new Error(`probeClick: no match for ${pattern} after ${nSteps} probes`)
}

const HANDLERS = {
  async goto(step, { page }) {
    await page.goto(step.url, { waitUntil: step.waitUntil || 'commit' })
  },

  async click(step, { page }) {
    await resolve(page, step).click({ timeout: step.timeout ?? DEFAULT_TIMEOUT })
  },

  async navClick(step, { page }) {
    // The commonest case by far: a named button inside the page's nav.
    await page.locator(step.within || 'nav')
      .getByRole('button', { name: step.name, exact: step.exact ?? true })
      .first().click({ timeout: step.timeout ?? DEFAULT_TIMEOUT })
  },

  async toggle(step, { page }) {
    await resolve(page, { ...step, role: step.role || 'switch' })
      .click({ timeout: step.timeout ?? DEFAULT_TIMEOUT })
  },

  async hover(step, { page }) {
    await resolve(page, step).hover({ timeout: step.timeout ?? DEFAULT_TIMEOUT })
  },

  async type(step, { page }) {
    await page.keyboard.type(step.text, { delay: step.delay ?? 70 })
  },

  async press(step, { page }) {
    await page.keyboard.press(step.key)
  },

  async wait(step) {
    await sleep(step.ms)
  },

  async waitForText(step, { page }) {
    await page.getByText(step.text, { exact: step.exact ?? false }).first()
      .waitFor({ timeout: step.timeout ?? 30000 })
  },

  async waitForSelector(step, { page }) {
    await page.locator(step.selector).first().waitFor({ timeout: step.timeout ?? 30000 })
  },

  async wheel(step, { page }) {
    const { dy = -500, dx = 0, times = 1, pauseMs = 350, at } = step
    const box = at ? await page.locator(at).boundingBox() : { x: 0, y: 0, ...page.viewportSize() }
    if (box) await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
    for (let i = 0; i < times; i++) {
      await page.mouse.wheel(dx, dy)
      await sleep(pauseMs)
    }
  },

  // One generic drag serves both an ordinary drag-and-drop and the 3D orbit
  // shot (right-button drag, moved in many small hops so the map animates
  // smoothly instead of teleporting).
  async drag(step, { page }) {
    const { button = 'left', path: legs = [], stepMs = 55, from } = step
    const box = from ? await page.locator(from).boundingBox() : { x: 0, y: 0, ...page.viewportSize() }
    if (!box) throw new Error(`drag: ${from} has no bounding box`)
    let x = box.x + box.width / 2
    let y = box.y + box.height / 2
    await page.mouse.move(x, y)
    await page.mouse.down({ button })
    try {
      for (const [dx, dy] of legs) {
        const hops = Math.max(1, Math.round(Math.max(Math.abs(dx), Math.abs(dy)) / 6))
        for (let i = 1; i <= hops; i++) {
          await page.mouse.move(x + (dx * i) / hops, y + (dy * i) / hops, { steps: 1 })
          await sleep(stepMs)
        }
        x += dx
        y += dy
      }
    } finally {
      await page.mouse.up({ button })
    }
  },

  async scrollPanel(step, { page }) {
    const to = step.to ?? 'bottom'
    await page.locator(step.selector).first().evaluate((el, to) => {
      el.scrollTop = to === 'bottom' ? el.scrollHeight : to === 'top' ? 0 : Number(to)
    }, to)
  },

  async screenshot(step, { page, outDir }) {
    const file = path.join(outDir, `${step.name || 'shot'}.png`)
    await page.screenshot({ path: file })
    return file
  },

  probeClick,

  async js(step, { page }) {
    return page.evaluate(step.code)
  },
}

export const STEP_TYPES = Object.keys(HANDLERS)

/** Run one step. Throws on failure — `runSteps` decides what to do about it. */
export async function runStep(step, ctx) {
  const handler = HANDLERS[step.do]
  if (!handler) throw new Error(`unknown step type "${step.do}"`)
  return handler(step, ctx)
}

/** A one-line description of a step, for logs and the dry-run report. */
export function describeStep(step) {
  const detail = step.name ?? step.selector ?? step.text ?? step.key
    ?? step.pattern ?? step.url ?? (step.ms != null ? `${step.ms}ms` : null)
  return detail ? `${step.do} "${detail}"` : step.do
}

/**
 * Run a scene's steps, tolerating failures.
 * @returns {Array<{step: string, ok: boolean, error?: string, ms: number}>}
 */
export async function runSteps(steps, ctx) {
  const results = []
  for (const step of steps || []) {
    const label = describeStep(step)
    const t0 = Date.now()
    try {
      await runStep(step, ctx)
      results.push({ step: label, ok: true, ms: Date.now() - t0 })
      ctx.log?.(`     ✓ ${label}`)
    } catch (e) {
      const msg = String(e.message || e).split('\n')[0].slice(0, 160)
      results.push({ step: label, ok: false, error: msg, ms: Date.now() - t0 })
      ctx.log?.(`     (skipped: ${label}) ${msg}`)
    }
  }
  return results
}
