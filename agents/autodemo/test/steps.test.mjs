import { test } from 'node:test'
import assert from 'node:assert/strict'
import { runStep, runSteps, describeStep, STEP_TYPES } from '../src/engine/steps.mjs'

/**
 * A mock Playwright page that records every call as a flat trace.
 * `fail` is a predicate over a trace entry; matching calls throw, which is how
 * the fault-tolerance tests simulate a renamed button.
 */
function mockPage({ panelText = '', boundingBox = { x: 0, y: 0, width: 1000, height: 800 }, fail = () => false } = {}) {
  const trace = []
  const rec = (name, ...args) => {
    const entry = { name, args }
    trace.push(entry)
    if (fail(entry)) throw new Error(`mock failure: ${name}`)
    return entry
  }
  const locator = sel => {
    const self = {
      first: () => self,
      locator: s => { rec('locator', `${sel} ${s}`); return locator(`${sel} ${s}`) },
      getByRole: (role, o) => { rec('getByRole', role, o, `within:${sel}`); return self },
      getByText: (t, o) => { rec('getByText', t, o, `within:${sel}`); return self },
      click: o => rec('click', sel, o),
      hover: o => rec('hover', sel, o),
      waitFor: o => rec('waitFor', sel, o),
      boundingBox: async () => { rec('boundingBox', sel); return boundingBox },
      evaluate: async (fn, arg) => {
        rec('evaluate', sel, arg)
        // Stand in for the panel element the probe/scroll steps read.
        return fn({ textContent: panelText, scrollHeight: 4000, scrollTop: 0 }, arg)
      },
    }
    return self
  }
  const page = {
    trace,
    locator: sel => { rec('locator', sel); return locator(sel) },
    getByRole: (role, o) => { rec("getByRole", role, o); return { first: () => ({ click: p => rec('click', o?.name, p), hover: p => rec('hover', o?.name, p), waitFor: p => rec('waitFor', o?.name, p) }) } },
    getByText: (t, o) => { rec('getByText', t, o); return { first: () => ({ waitFor: p => rec('waitFor', t, p), click: p => rec('click', t, p) }) } },
    goto: (url, o) => rec('goto', url, o),
    screenshot: o => rec('screenshot', o),
    evaluate: code => rec('evaluate-page', code),
    viewportSize: () => ({ width: 1000, height: 800 }),
    keyboard: {
      type: (t, o) => rec('type', t, o),
      press: k => rec('press', k),
    },
    mouse: {
      move: (x, y, o) => rec('move', Math.round(x), Math.round(y), o),
      down: o => rec('down', o?.button),
      up: o => rec('up', o?.button),
      click: (x, y) => rec('mouse-click', Math.round(x), Math.round(y)),
      wheel: (dx, dy) => rec('wheel', dx, dy),
    },
  }
  return page
}

const ctx = (page, extra = {}) => ({ page, vars: {}, outDir: '/tmp', log: () => {}, ...extra })

const names = page => page.trace.map(e => e.name)
const find = (page, name) => page.trace.filter(e => e.name === name)

test('every documented step type has a handler', () => {
  for (const t of ['click', 'navClick', 'toggle', 'type', 'press', 'hover', 'wait',
    'waitForText', 'waitForSelector', 'wheel', 'drag', 'scrollPanel',
    'screenshot', 'probeClick', 'js', 'goto']) {
    assert.ok(STEP_TYPES.includes(t), `missing handler: ${t}`)
  }
})

test('click prefers an accessible role+name over a CSS selector', async () => {
  const page = mockPage()
  await runStep({ do: 'click', role: 'button', name: 'Dashboard' }, ctx(page))
  const [role] = find(page, 'getByRole')
  assert.equal(role.args[0], 'button')
  assert.equal(role.args[1].name, 'Dashboard')
})

test('click falls back to a selector when one is given', async () => {
  const page = mockPage()
  await runStep({ do: 'click', selector: '#submit' }, ctx(page))
  assert.ok(find(page, 'locator').some(e => e.args[0] === '#submit'))
  assert.equal(find(page, 'getByRole').length, 0)
})

test('a click with nothing to click is an error, not a silent no-op', async () => {
  await assert.rejects(() => runStep({ do: 'click' }, ctx(mockPage())), /needs one of/)
})

test('navClick scopes to the nav and matches the name exactly', async () => {
  const page = mockPage()
  await runStep({ do: 'navClick', name: 'Reports' }, ctx(page))
  assert.ok(find(page, 'locator').some(e => e.args[0] === 'nav'))
  const role = find(page, 'getByRole').at(-1)
  assert.equal(role.args[1].name, 'Reports')
  assert.equal(role.args[1].exact, true)
})

test('toggle defaults to the switch role', async () => {
  const page = mockPage()
  await runStep({ do: 'toggle', name: 'Dark mode' }, ctx(page))
  assert.equal(find(page, 'getByRole').at(-1).args[0], 'switch')
})

test('type and press go through the keyboard', async () => {
  const page = mockPage()
  await runStep({ do: 'type', text: 'hello', delay: 10 }, ctx(page))
  await runStep({ do: 'press', key: 'Control+k' }, ctx(page))
  assert.deepEqual(find(page, 'type')[0].args[0], 'hello')
  assert.equal(find(page, 'press')[0].args[0], 'Control+k')
})

test('wheel scrolls the requested number of times', async () => {
  const page = mockPage()
  await runStep({ do: 'wheel', dy: -500, times: 4, pauseMs: 0 }, ctx(page))
  const wheels = find(page, 'wheel')
  assert.equal(wheels.length, 4)
  assert.deepEqual(wheels[0].args, [0, -500])
})

test('drag presses the named button, moves in small hops, and releases', async () => {
  const page = mockPage()
  await runStep({ do: 'drag', button: 'right', path: [[0, -120]], stepMs: 0 }, ctx(page))
  const seq = names(page)
  assert.ok(seq.indexOf('down') < seq.indexOf('up'))
  assert.equal(find(page, 'down')[0].args[0], 'right')
  assert.equal(find(page, 'up')[0].args[0], 'right')
  // 120px at ~6px a hop, plus the initial positioning move.
  assert.ok(find(page, 'move').length >= 20, `only ${find(page, 'move').length} moves`)
})

test('drag releases the mouse even when a move throws', async () => {
  // Otherwise a failed orbit leaves the button held down and every later
  // step in the render clicks-and-drags instead of clicking.
  // Fail partway through the drag, not on the move that positions the cursor
  // before the button goes down.
  let moves = 0
  const page = mockPage({ fail: e => e.name === 'move' && ++moves > 3 })
  await assert.rejects(() => runStep({ do: 'drag', path: [[0, -200]], stepMs: 0 }, ctx(page)))
  assert.equal(find(page, 'up').length, 1)
})

test('scrollPanel to bottom sets scrollTop to the full scroll height', async () => {
  const page = mockPage()
  await runStep({ do: 'scrollPanel', selector: '#panel', to: 'bottom' }, ctx(page))
  assert.equal(find(page, 'evaluate').at(-1).args[1], 'bottom')
})

test('probeClick clicks outward until the panel matches, and saves the hit', async () => {
  const page = mockPage({ panelText: 'Water main WM-K12.4 · Burst' })
  const c = ctx(page)
  const hit = await runStep({
    do: 'probeClick', pattern: '(W[MD]-K[0-9.]+)', panel: 'aside',
    saveAs: 'pipe', settleMs: 0,
  }, c)
  assert.equal(hit, 'WM-K12.4')
  assert.equal(c.vars.pipe, 'WM-K12.4')
  assert.ok(find(page, 'mouse-click').length >= 1)
})

test('probeClick skips a hit the run has already used', async () => {
  const page = mockPage({ panelText: 'Water main WM-K12.4' })
  const c = ctx(page, { vars: { pipe: 'WM-K12.4' } })
  // Every probe returns the excluded id, so it must exhaust the spiral.
  await assert.rejects(() => runStep({
    do: 'probeClick', pattern: '(W[MD]-K[0-9.]+)', panel: 'aside',
    excludeMatch: 'pipe', settleMs: 0, spiral: { steps: 5 },
  }, c), /no match/)
})

test('probeClick gives up after the configured number of probes', async () => {
  const page = mockPage({ panelText: 'nothing here' })
  await assert.rejects(() => runStep({
    do: 'probeClick', pattern: 'NOPE', panel: 'aside', settleMs: 0, spiral: { steps: 7 },
  }, ctx(page)), /no match for NOPE after 7 probes/)
})

test('probeClick stays inside the region it was given', async () => {
  const page = mockPage({ panelText: 'no', boundingBox: { x: 300, y: 100, width: 400, height: 300 } })
  await assert.rejects(() => runStep({
    do: 'probeClick', pattern: 'NOPE', panel: 'aside', region: '.map',
    settleMs: 0, spiral: { steps: 60, radiusStep: 10 },
  }, ctx(page)))
  for (const { args: [x, y] } of find(page, 'mouse-click')) {
    assert.ok(x >= 308 && x <= 692, `x ${x} escaped the region`)
    assert.ok(y >= 108 && y <= 392, `y ${y} escaped the region`)
  }
})

test('an unknown step type is an error', async () => {
  await assert.rejects(() => runStep({ do: 'teleport' }, ctx(mockPage())), /unknown step type/)
})

test('a failed step is skipped and the rest of the scene still runs', async () => {
  const page = mockPage({ fail: e => e.name === 'click' && e.args[0] === 'Missing' })
  const results = await runSteps([
    { do: 'press', key: 'a' },
    { do: 'click', name: 'Missing' },
    { do: 'press', key: 'b' },
  ], ctx(page))
  assert.deepEqual(results.map(r => r.ok), [true, false, true])
  assert.match(results[1].error, /mock failure/)
  assert.deepEqual(find(page, 'press').map(e => e.args[0]), ['a', 'b'])
})

test('the dry-run report names the step that failed', async () => {
  const page = mockPage({ fail: e => e.name === 'click' })
  const [r] = await runSteps([{ do: 'click', name: 'Checkout' }], ctx(page))
  assert.equal(r.step, 'click "Checkout"')
  assert.equal(r.ok, false)
})

test('describeStep labels each step by its most identifying field', () => {
  assert.equal(describeStep({ do: 'click', name: 'Go' }), 'click "Go"')
  assert.equal(describeStep({ do: 'wait', ms: 500 }), 'wait "500ms"')
  assert.equal(describeStep({ do: 'press', key: 'Enter' }), 'press "Enter"')
  assert.equal(describeStep({ do: 'probeClick', pattern: 'W-\\d+' }), 'probeClick "W-\\d+"')
  assert.equal(describeStep({ do: 'screenshot' }), 'screenshot')
})
