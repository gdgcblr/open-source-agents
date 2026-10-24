---
name: autodemo
description: Record a narrated, captioned demo video of a running web app. Use when the user asks for a demo video, screen recording, narrated walkthrough, product video, launch video, screencast, or "record a demo of my app" — and when they want to write or repair an autodemo.config.yaml scene file.
---

# Recording a demo video with autodemo

`autodemo` drives a running web app through a scripted walkthrough, narrates it,
and cuts an MP4. You write (or generate) a scene file; the engine does the rest.

**The app must already be running.** autodemo does not start dev servers, seed
databases, or log anyone in. Confirm the URL responds before anything else.

## The workflow

Follow these in order. Do not skip step 4 — a full render costs real minutes of
wall-clock time, and narration is the thing users always want to change.

1. **Preflight.** `autodemo preflight --config <file>` — checks ffmpeg, ffprobe,
   a browser, the app URL and the TTS engine. Fix every ✗ before continuing.
2. **Get a scene file.** Either scaffold one (`autodemo init`) and fill it in, or
   — much better when the app is unfamiliar — delegate to the `demo-scripter`
   subagent, which opens the app, reads its accessibility tree, and writes a
   config with selectors that actually exist.
3. **Dry-run.** `autodemo render --config <file> --dry-run`. This runs the whole
   walkthrough with no TTS and no encoding, and prints ✓ or `(skipped: …)` per
   step. Repair every skipped step and re-run. Iterate here, not in full renders.
4. **Show the narration to the user and get approval.** Print the narration of
   every scene as plain prose and ask them to confirm or edit it. A full render
   of a wrong script wastes minutes and they will ask for it again anyway.
   Never skip this because the script "looks fine".
5. **Render.** `autodemo render --config <file>`. Report the output path, the
   duration, and any steps that were skipped during the real run.

## Writing the scene file

The config schema, defaults and every step type are documented in
`references/step-types.md`. Read it before writing or repairing a config.

Narration is the part that makes a demo watchable or unwatchable; the rules are
in `references/writing-narration.md`. Read it before writing any narration.

The shape, in brief:

```yaml
app:   { url: http://localhost:5173/, viewport: { width: 1600, height: 900 } }
voice: { engine: edge-tts, voice: en-US-AriaNeural }
output:{ dir: ./autodemo-out, file: demo.mp4 }
scenes:
  - id: intro
    layout: title          # full-screen card
    title: "My App"
    subtitle: "What it does"
    narration: "This is My App. Let me show you what it can do."
    steps: []
  - id: dashboard
    layout: caption        # lower third
    title: "The dashboard"
    narration: "The dashboard pulls everything into one view."
    steps:
      - { do: navClick, name: "Dashboard" }
      - { do: waitForText, text: "Total revenue" }
      - { do: wait, ms: 1500 }
```

### Rules that matter

- **Each scene holds for as long as its narration.** You do not pad scenes by
  hand. After the steps finish, the engine waits out the rest of the voice clip.
  So: write the narration for the beat you want, and add only the steps needed
  to show it. Over-padding with `wait` makes the video drag.
- **Prefer `getByRole` targeting** — `{ do: click, role: button, name: "Save" }`
  — over CSS selectors. Role-and-name survives a restyle; `.btn-primary-2` does not.
- **Steps are individually fault-tolerant.** A failed step is logged and skipped,
  never fatal. That is a safety net for a long render, not permission to leave
  broken steps in a config: a skipped step means a dead patch of video.
- **Scene ids must be unique.** They key the audio clips.
- **Canvas and map apps** have no DOM to target. Use `probeClick`, which clicks
  in an expanding spiral until a panel's text matches a pattern. See the
  reference and `examples/map-app/`.

## Repairing a dry-run

Every `(skipped: …)` line names the step. Common causes, in order of likelihood:

| Symptom | Fix |
|---|---|
| `click "Foo"` timed out | The accessible name is wrong. Re-read the snapshot; match the *visible* text, and try `exact: false`. |
| `waitForText` timed out | The text is split across elements, or the view needs longer. Raise `timeout`, or wait for a stabler substring. |
| `navClick` timed out | The nav is not a `<nav>`. Pass `within: "header"` or whatever the real container is. |
| `scrollPanel` did nothing | The selector is the inner content, not the scrolling box. Target the element with `overflow: auto`. |
| `probeClick` found no match | Widen the `spiral.steps`, raise `radiusStep`, or loosen the `pattern`. |

`references/troubleshooting.md` covers render-time and encode-time problems.

## Reporting back

After a render, tell the user: the output path, the runtime, the scene count,
and — explicitly — any steps that were skipped, because those are the dull
patches in their video. Do not report a render as clean if steps were skipped.
