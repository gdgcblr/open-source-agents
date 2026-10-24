# Step types and config reference

Every step is `{ do: <type>, ...fields }`. Unknown types and missing required
fields are rejected by the JSON Schema when the config loads, before anything
is rendered.

## Targeting

Most interactive steps accept the same targeting fields, tried in this order:

| Field | Meaning |
|---|---|
| `selector` | A CSS selector. Last resort — it breaks on restyles. |
| `role` + `name` | Playwright `getByRole`. **Prefer this.** |
| `name` alone | Shorthand for `role: button`. |
| `text` | `getByText`, for non-interactive content. |
| `within` | A CSS selector to scope the search to. |
| `exact` | Match the accessible name exactly (default `false`). |
| `timeout` | Milliseconds before the step is skipped (default 15000). |

## The step table

| `do` | Fields | What it does |
|---|---|---|
| `click` | targeting | Clicks one element. |
| `navClick` | `name`, `within` (default `nav`), `exact` (default `true`) | Clicks a named button inside the nav. The commonest step in any demo. |
| `toggle` | `name`, `role` (default `switch`) | Flips a switch by its accessible name. |
| `type` | `text`, `delay` (default 70) | Types into the focused element, one key at a time, so it reads as typing on camera. |
| `press` | `key` | A key or chord: `Enter`, `Control+k`, `Escape`. |
| `hover` | targeting | Hovers — use it to open a menu or show a tooltip. |
| `wait` | `ms` | Dead time. Use sparingly; scenes already hold for their narration. |
| `waitForText` | `text`, `timeout` (default 30000), `exact` | Waits for text to appear. The right way to wait for data to load. |
| `waitForSelector` | `selector`, `timeout` | Waits for an element to exist. |
| `wheel` | `dy` (default -500), `dx`, `times`, `pauseMs` (350), `at` | Mouse wheel, repeated. Negative `dy` zooms a map in. |
| `drag` | `button` (`left`\|`right`), `path: [[dx,dy],…]`, `stepMs` (55), `from` | Presses, moves through each leg in small hops, releases. Right-button drag is how you pitch and orbit a 3D map. |
| `scrollPanel` | `selector`, `to`: `bottom`\|`top`\|`<px>` | Scrolls a specific scroll container. |
| `screenshot` | `name` | Writes `<name>.png` into the output dir. For README images. |
| `probeClick` | see below | Clicks until something is selected. |
| `js` | `code` | `page.evaluate`. The escape hatch. |
| `goto` | `url`, `waitUntil` | Navigates. The caption overlay is reinstalled on the next scene. |

## `probeClick` — the one that makes canvas apps demoable

A map, a chart, a WebGL scene: the features have no DOM nodes, so there is
nothing to `getByRole`. `probeClick` clicks outward in an expanding spiral from
the centre of the viewport (or of `region`) until the text inside `panel`
matches `pattern`.

```yaml
- do: probeClick
  pattern: "(W[MD]-K[0-9.-]+)"        # a regex; capture group 1 is the result
  panel: 'aside[aria-label="Asset inspector"]'
  region: ".map-container"            # confine probing to the canvas
  saveAs: firstPipe                   # store the hit in a run-scoped variable
  spiral: { steps: 160, radiusStep: 2.5, angleStep: 0.7 }
  settleMs: 220                       # time for the panel to update after a click
```

A later scene can then select a *different* feature:

```yaml
- { do: probeClick, pattern: "(W[MD]-K[0-9.-]+)", panel: "aside", excludeMatch: firstPipe }
```

Tuning: raise `spiral.steps` if it gives up; raise `radiusStep` to sweep a wider
area with the same number of probes; raise `settleMs` if the panel updates
asynchronously. `region` matters — without it the spiral wanders over the
sidebar and clicks your own UI.

## Config reference

```yaml
app:
  url: http://localhost:5173/     # required
  viewport: { width: 1600, height: 900 }
  chromePath: auto                # auto | <path>; env CHROME_PATH wins
  waitForSelector: "#root"        # readiness probe before scene 1
  headless: true
  colorScheme: dark               # light | dark | no-preference

voice:
  engine: edge-tts                # edge-tts | sapi | none
  voice: en-US-AriaNeural         # any edge-tts voice
  rate: "+0%"                     # e.g. "-10%" to slow down
  tailMs: 750                     # silence held after each narration clip

theme:
  accent: "#7dd3fc"
  font: "Inter, Segoe UI, system-ui, sans-serif"
  position: bottom                # bottom | top — where the caption sits
  eyebrow: "My Product"           # small uppercase line on the title card

output:
  dir: ./autodemo-out             # relative to the config file
  file: demo.mp4
  crf: 20                         # lower is better quality, bigger file
  preset: medium
  thumbnail: true

outro:
  title: "Try it yourself"
  subtitle: "example.com"
  holdMs: 3500

scenes:
  - id: intro                     # required, unique, [a-zA-Z0-9_-]
    layout: title                 # title | caption | none
    title: "..."
    subtitle: "..."
    narration: "..."              # spoken; also sets how long the scene holds
    steps: []
```

### Voice engines

- `edge-tts` — neural voices, any OS, needs `pip install edge-tts`. Default.
- `sapi` — Windows System.Speech. No install, noticeably more robotic.
- `none` — silent clips sized to the narration text at ~165 wpm. The pacing is
  real, the audio is silent. Use it in CI and when iterating on timing.

If `edge-tts` is selected but unavailable, the engine falls back to SAPI on
Windows and to silence elsewhere, and says so in the log. It never fails the
render over a missing voice.
