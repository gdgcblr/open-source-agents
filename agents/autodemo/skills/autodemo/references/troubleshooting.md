# Troubleshooting

## Preflight

**`✗ ffmpeg` / `✗ ffprobe`** — both ship together.
`winget install Gyan.FFmpeg` · `brew install ffmpeg` · `sudo apt-get install -y ffmpeg`.
Reopen the shell afterwards on Windows so the new PATH is picked up.

**`✗ app URL`** — autodemo does not start your server. Start it, confirm the URL
in a browser, then re-run. A `401`/`403` is reported as reachable: autodemo will
record your login page, so log in first with a persistent profile, or point it
at an unauthenticated route.

**`✗ browser`** — a `chromePath` was set and does not exist. Either fix it, set
`chromePath: auto`, or install Playwright's chromium with
`npx playwright install chromium`. "system Chrome not found" is a ✓, not a ✗:
the bundled chromium is used.

**`voice: edge-tts missing`** — `pip install -U edge-tts`. This is a warning,
not a failure: Windows falls back to SAPI, other platforms to silent clips.

## Dry-run failures

See the table in `SKILL.md` for the per-step causes. Two that recur:

**Everything times out.** The app never finished loading. Set
`app.waitForSelector` to something that only exists once the app is interactive,
and give the first scene a `waitForText` on real content rather than a bare `wait`.

**The first scene works and nothing after it does.** A step navigated the page
away, or a modal is intercepting clicks. Add `{ do: press, key: "Escape" }` at
the top of the next scene.

## Render-time

**The video is much longer than the narration.** Something held open — usually a
`wait` left over from debugging, or a `waitForText` that timed out at 30s. The
per-scene log line shows where the time went.

**Captions never appear.** The overlay is injected into the page; a navigation
wipes it. It is reinstalled at the start of each scene, so a `goto` *inside* a
scene loses the caption for the rest of that scene. Put navigations at the end
of a scene, or give them a scene of their own.

**Captions appear behind the app.** The overlay sits at `z-index: 2147483000`.
An app using a higher z-index will cover it; lower that element, or set
`theme.position: top` if the clash is only with a bottom bar.

**The audio is silent.** Check the `[1/3]` log lines. `silent fallback: <id>`
means TTS failed for that scene and a silent clip of the right length was used
instead, so the video is correctly paced but has no voice.

**The audio drifts out of sync.** Marks are wall-clock offsets taken during the
recording, so a machine that stalls mid-record (a heavy rebuild, a GC pause)
can drift. Close other work and re-render; this is why the recording is one
continuous take rather than per-scene clips.

**Only the first scene has audio.** The filter graph collapsed — check that each
scene has a distinct `id`. Duplicate ids are rejected at load time, so this
should not happen with a config that validates.

## Platform

**Linux/CI**: the launcher uses `--use-gl=angle --use-angle=swiftshader
--no-sandbox`. Software rendering is slow for WebGL-heavy apps; expect a map
demo to take several times longer on a runner than on a laptop.

**WSL**: no GPU and no system Chrome by default. Run
`npx playwright install --with-deps chromium`.

**macOS**: the first run prompts for screen-recording permission even headless.
Grant it to the terminal, not to Chrome.

## Getting a clean recording

- Close dev tools and extensions — a persistent Chrome profile brings its
  toolbars into the recording. The default fresh context is clean.
- Seed the app with realistic data. An empty-state demo shows nothing.
- `viewport: { width: 1600, height: 900 }` renders 16:9 without letterboxing.
- Raise `output.crf` to 28 for a quick draft; drop it to 18 for the final cut.
