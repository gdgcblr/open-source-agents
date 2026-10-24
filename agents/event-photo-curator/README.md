# AfterClick

AfterClick is a local-first, privacy-focused app that helps organisers turn an overwhelming event gallery into a varied shortlist of memorable moments, and lets attendees find photos featuring themselves through opt-in face matching. Built for ease of use, it combines local Gemma 4 vision with OpenCV and ImageHash to assess photos, group similar shots, suggest captions, and preserve original-quality downloads—saving everyone time on the eternal “which one should I post?”

[View the AfterClick pitch deck and UI flows](AfterClick-Demo.pdf)

## Overview

### Problem Statement & Intended Users

Organizers and attendees need a shared view of an event, a varied shortlist for social posts, and an easy way to find photos featuring themselves or their organizing team. This self-contained Python project provides a CLI and a loopback-only, single-event laptop pilot. It is being tested locally before publication; it is not a hosted multi-user service.

### Key Features

- Import JPEG, PNG, HEIC/HEIF and optional Fujifilm RAF embedded JPEGs. Original files are never edited or deleted.
- Compute sharpness, exposure and perceptual similarity locally. These are **review-order and diversity hints, not hard quality rejection rules**.
- Review every readable image with local Gemma 4 vision via Ollama, including technically weak frames. AI rates moment, composition and expressions, explains its judgment, and suggests captions.
- Prefer different visual groups when choosing top N; AI scores choose the representative. Remaining slots can include additional frames from a group. All photos remain accessible.
- Paginated gallery, cached 1024px WebP gallery previews, original downloads, ZIP of picks, and separate full-resolution JPEG watermark/credit exports.
- Opt-in personal, organizing-team, or strict one-to-one face comparison using local OpenCV models. Original-derived 2048px face inputs, versioned indexes, normalized face boxes, and ambiguity flags. Temporary reference images are not saved; the event face index can be cleared.
- Explicit mock mode for workflow testing, bounded local AI loops, caching, time budget and cooperative cancellation. No automatic cloud fallback.

## Technical Stack

- **Runtime:** Python 3.11+, Typer, Rich, FastAPI, Uvicorn, SQLite (standard library).
- **Images:** Pillow, pillow-heif, OpenCV headless, NumPy, ImageHash. Optional rawpy extracts RAF JPEG previews; no RAW demosaicing.
- **Visual editor:** Google Gemma 4 through local Ollama, default `gemma4:e2b-it-q4_K_M`. Model choice is explicit. The same lightweight default is used on this 16 GB development laptop; 48 GB is not required.
- **Face matching:** OpenCV Zoo YuNet detection and SFace embeddings. This is separate from Gemma's editorial judgment.
- **Optional providers:** `mock` ranks only by sharpness and labels its output; explicit `gemini` uses google-genai and requires an API key. The web pilot exposes local Ollama and mock only.
- **Interface:** a dark React UI with vendored beUI buttons and inputs, built with Vite/Tailwind and served by FastAPI. Prebuilt assets are included; ordinary use needs no Node.js. See [frontend development](frontend/README.md).

## Architecture & Data Flow

### What makes this an agent

The organizer chat is a custom Python tool-calling agent, not just a fixed vision pipeline. Local Gemma 4 chooses among `inspect_event`, `visual_search`, `count_faces`, and `get_shortlist` using Ollama's native function-calling protocol. Python validates and executes the tool, returns observations to Gemma, and asks for a final response. Returned photo IDs come from actual tool results. Tool traces are returned by the API and CLI; the compact UI shows task progress and photo results. No ADK, LangGraph or Agents SDK is required by this repository or used here.

The loop allows at most four model turns, rejects unknown tools/extra arguments, stops repeated identical calls, checks cancellation/deadlines between calls, and never exposes a shell or publishing action. Visual search caches decisions by image hash, query, model and version. Face-count search detects faces without retaining identity embeddings. Curation remains a separate bounded inspect/review/select/export pipeline. Conversations currently handle independent requests rather than persistent follow-up memory.

### Technology inventory

Python 3.11+; custom Python/Ollama tool orchestration; local Gemma 4 E2B; FastAPI/Uvicorn; SQLite; OpenCV YuNet/SFace; Pillow, pillow-heif, ImageHash, NumPy; Typer/Rich; python-dotenv. Optional google-genai/Gemini and rawpy. The UI uses React, JavaScript/TypeScript, Vite, Tailwind, Motion, lucide-react and vendored beUI components with MIT attribution. Tests use pytest/httpx and Node's test runner with React server rendering.


```text
Read-only folder OR local browser upload
  → decode/orient → 1024px AI preview + technical hints + pHash groups
  → review queue: ordinary frames first, flagged frames later
  → cached assessment OR local Ollama image review
  → validate structured output and IDs → persist completed scores
  → AI ranking + soft visual-diversity preference
  → untouched original copies / gallery shortlist / CSV + HTML

Opt-in reference image(s)
  → local YuNet/SFace embeddings (references never saved)
  → compare with cached event embeddings → possible matches
```

The agent runs the job from inspection through selection and export. The UI is an interaction layer over that workflow, not a second agent. Math helps prioritize work, but a soft image with a strong moment can beat a technically sharp frame. Unreadable files cannot be reviewed and receive an error reason. Exact-content duplicates share a cached assessment.

The bounded loop reviews images sequentially on a laptop, validates responses, caches completed work, checks cancellation/time limits between images, and finalizes picks only after a full successful pass. Failed/cancelled web reviews retain the previous shortlist. The first local review is slower; cached reruns avoid inference while still rechecking local files.

## Prerequisites

- Python 3.11+ and pip/venv; enough disk space for original copies and local models.
- [Ollama](https://ollama.com/download) with a local Gemma 4 vision model. Initial model installation requires internet and several GB of disk space; subsequent inference is local.
- HEIC codecs from the declared pillow-heif dependency. RAF additionally needs rawpy and an embedded JPEG supported by that decoder.
- A 16 GB Apple Silicon laptop is the current test machine. Performance on 8 GB machines has not been established. More RAM permits larger models; it does not guarantee faster review.

## Installation & Setup

The app runs locally; no hosted deployment is required. To review this contribution from the feature branch:

```bash
git clone --branch feat/event-photo-curator https://github.com/OveRide-Phoenix/open-source-agents.git
cd open-source-agents/agents/event-photo-curator
```

After it is merged, use a normal clone of `gdgcblr/open-source-agents` instead. Install in an isolated environment:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
ollama serve                 # separate terminal, if Ollama is not already running
ollama pull gemma4:e2b-it-q4_K_M
python -m curator models     # optional face search, about 39 MB, checksums verified
python -m curator doctor
```

Ollama is a separate runtime and is not installed by pip. On macOS it can also be installed with `brew install ollama`. The UI does not automatically download larger models. `curator doctor` reports actual installed model readiness without loading one or sending images.

Optional RAF decoder:

```bash
python -m pip install 'rawpy>=0.24,<1'
```

Optional cloud provider only:

```bash
cp .env.example .env
# Set GEMINI_API_KEY locally; never commit .env.
```

The default Ollama path needs no key and never falls back to Gemini. All commands run from this project directory.

## Configuration & Environment Variables

| Setting | Default | Meaning |
| :--- | :--- | :--- |
| `--provider` | `ollama` | CLI: `ollama`, `mock`, or explicitly selected `gemini`. |
| `--model` | `gemma4:e2b-it-q4_K_M` | Explicit local vision model. For the optional Gemini provider, pass `--model gemini-2.5-flash`. |
| `--top` | `15` | Maximum picks; fewer if fewer readable photos. |
| `--out` | `./picks` | New/empty output folder, separate from the entire input tree; never overwrites a prior selection. |
| `--blur-threshold` | `100` | Laplacian variance below which a technical hint is added, on max-1024px grayscale. Does not exclude from AI. |
| `--exposure-percent` | `20` | Add a hint if more than this percentage of grayscale pixels are ≤5 or ≥250. Does not exclude from AI. |
| `--dup-distance` | `6` | Distance between 64-bit pHashes for a connected similarity group. Groups only guide diversity. |
| `--batch-size` | `1` | CLI provider batch size, 1–16. One image at a time is the laptop default. |
| `--cache-dir` | `./.cache` | CLI assessment cache. Web cache lives inside the event data directory. |
| `--caption-style` | Casual event Instagram, no hashtag spam | Caption guidance; mock captions remain placeholders. |
| `GEMINI_API_KEY` | Unset | Only for explicitly selected Gemini. Missing/placeholder keys warn and switch that provider to mock. Invalid real keys fail visibly. |
| `serve --data` | `.local-event` | Dedicated private event directory; chmod 700, SQLite, original copies, thumbnails, previews and scores. |
| `serve --port` | `8787` | Loopback-only port; no public bind option. |

The local gallery enforces a maximum of 500 photos per event, a maximum of 100 files/500 MB per upload batch, and a 100 MB limit per original. Only one face-index/search job can load at once. The web review has a configurable 1–120 minute budget (default 30), at most 500 event photos, and one active review. Stop/time budget checks happen **between** images; an active Ollama request has a 180-second timeout and cannot be instantly cancelled. Up to three attempts handle malformed local results and transient server errors. CLI local requests use the same bounded retry path; its overall folder run is not time-budgeted.

Cache keys include SHA-256 of source bytes, provider, model tag, caption style and pipeline version. Changing files/model/style invalidates entries; changing top N reuses scores. If you replace model weights under the same Ollama tag, clear the score cache to force reevaluation. Cache files contain descriptions/captions, not images or keys. They remain private event data.

## How to Run

### Local browser pilot

Open `/organizer` for directory import, actual job progress and tool-calling chat; open `/attendee` for photos and opt-in face search. These are separate local workflows, **not authentication or access control**. The attendee screen hides organizer controls. Start with [the short demo script](DEMO.md).

Directory imports accept an explicitly supplied local folder and permission confirmation, copy supported files recursively, skip symlinks/event storage, and allow at most 500 candidate photos. An import is time-bounded and can be stopped between files. No source file is modified. Photographer credit is supplied by the organizer, not inferred.


The browser UI runs on your laptop with the Python agent; no hosted deployment is required. The project includes the served UI under `curator/static/`, so starting the current app does not require Node.js or a frontend build. Its React source and vendored beUI components live under `frontend/`.

```bash
python -m curator serve
# Open http://127.0.0.1:8787 in your browser.
```

1. Add photos with a photographer credit and permission confirmation. Organizer/attendee are contribution labels in this pilot, not authenticated roles.
2. Browse the gallery using cached 1024px WebP images. Opening a photo loads a separately cached 2048px WebP display preview. Originals download on demand. Existing events regenerate these previews lazily from originals; AI still uses its separate 1024px input.
3. Run local AI curation; keep browsing while it reviews all frames. A second review reuses completed cached scores.
4. View the shortlist, download untouched originals/ZIP, or create a separate credited/watermarked JPEG.
5. For face search, provide consenting reference images. Personal references must each contain exactly one face; team references can contain several consenting faces. Results are labelled **possible matches**, not verified identities.
6. Clear the face index when no longer needed. Reference selfies never enter event storage.

### Video demonstration and eventual contribution

The planned demonstration is a video of the local app, uploaded by the project owner. Show credited photo import, fast thumbnail browsing, an actual local AI review including poor-quality frames, the diverse shortlist, and an original/watermarked download. Demonstrate face search only with consenting reference subjects. Include model/hardware details and distinguish a cached rerun from first-pass inference.

When publication is explicitly authorized, include both the agent backend and local UI source/assets in this project directory so others can reproduce the demonstration on their laptops. Exclude private photos, references, caches, event storage, model weights, dependencies, and secrets. A video supplements runnable code; it does not replace setup instructions. Demo-video upload and deployment remain separate actions; neither is performed automatically.

### CLI

```bash
python -m curator run ./photos --out ./picks --top 15 \
  --provider ollama --model gemma4:e2b-it-q4_K_M \
  --blur-threshold 100 --dup-distance 6 \
  --caption-style "GDG Cloud Bengaluru Instagram, casual, no hashtag spam"
```

CLI output is selected original files, `report.csv`, and a self-contained offline `report.html` contact sheet including all readable previews and rejection reasons. Unsupported files are ignored; supported but unreadable files get CSV/HTML error rows. CSV columns:

```text
filename,sharpness,exposure flag,duplicate group,ai score,reason,caption,picked
```

### Cost and efficiency

Local Ollama has no per-token cloud API bill, but uses download bandwidth, local RAM, compute and energy. Reviews are sequential to bound memory/concurrency. All readable photos eventually reach AI, so technical triage changes the order rather than saving inference by silently throwing away moments. Cache hits avoid repeat inference. Gallery pages return at most 100 metadata records; default 48, with cached 1024px WebP gallery previews. Full-size originals are never embedded in listing JSON or fetched for ordinary gallery browsing. ZIPs are built on disk without recompressing already compressed originals.

Gemma requests use a bounded context, disabled thinking, short structured responses and a 1024px maximum image edge. Exact content duplicates reuse scores. The token summary uses Ollama prompt/output counts or successful Gemini response usage; it is not a billing ledger. Optional Gemini use follows its [pricing](https://ai.google.dev/gemini-api/docs/pricing); it is never selected automatically from a failed local request.

## Example Input & Output

### Example Input

```bash
python tests/generate_sample.py sample-photos
python -m curator run sample-photos --out sample-output-ai-queue --top 2 \
  --provider mock --cache-dir .cache/queue-v2
```

### Example Output

Actual local mock run after changing technical rejection to advisory hints:

```text
Provider: mock | Model: sharpness-v1
Scanned                 6
Blurry                  1
Dupes                   2
Exposure issues         1
Unreadable              0
Picked                  2
Cache hits              0
Estimated tokens used   0
```

All six readable images received scores, including the blurry and clipped frames. The two picks are `01-sharp.png` and `05-scene.png`. Mock score is `1 + 9 × sharpness / (sharpness + 1000)`; it explicitly makes no visual judgment and emits placeholder captions. Counts overlap because a blurry frame also belongs to a duplicate group. Images are generated patterns, not real event photos.

A real OpenCV check with local, public OpenCV sample images found cosine similarity 0.985 for a brightness-adjusted reference and 0.130 for a different test face, against a pilot threshold of 0.45. This is a narrow plumbing check, not a face-recognition accuracy benchmark. The downloaded source images stay in ignored `.cache`, not in the contribution.

Real local Ollama validation completed on this 16 GB Mac. A first image request returned valid JSON in 6.42 seconds with 408 local tokens. A four-photo CLI run reviewed all four, flagged one blurry frame, picked two and used 1,677 local tokens; an identical rerun had four cache hits and zero new tokens. A complete live backend run imported two public test photos, reviewed both using Ollama, selected one, returned one face match, produced a ZIP, and verified byte-identical original download. That backend run took 3.44 seconds and used 841 local tokens. These small fixture runs verify the plumbing, not curation accuracy or sustained throughput on a real event.

## How to Test

For the organizer walkthrough and expected results, follow [the local test flow](TEST-FLOW.md).

```bash
python -m pip install 'pytest>=8,<10' 'httpx>=0.28,<1'
python -m pytest -q
```

Generated fixtures cover blur/exposure measurements, grouping, rescue of a soft but highly AI-rated frame, model response validation, bounded retries, cache reuse, image orientation/metadata, HEIC, simulated RAF, CLI/report output, HTML/CSV injection protection, consent, uploads, pagination, original integrity, watermark attribution, ZIP downloads, loopback sessions/CSRF, cancellation and failure recovery. The current automated suite has 73 passing cases on Python 3.12; the earlier 54-case suite also passed on Python 3.11. Tests make no real AI/network requests. Model download and manual inference checks are separate.

A repeatable synthetic ingestion benchmark is available with `python -m tests.benchmark_local`. On this 16 GB macOS laptop, 100 generated 960×640 JPEGs imported in 2.06 seconds; the 48-photo metadata response was 12,865 bytes and took 1.6 ms in the local test client. All thumbnails totalled 4,242,970 bytes versus 50,323,645 bytes of originals (8.4%). These historical figures used the former 480px/quality-75 thumbnails; they do not describe the current higher-quality preview setting or real-event AI throughput.

Frontend changes can be checked with Node.js 20.19+ or 22.12+:

```bash
npm ci --prefix frontend
npm run build --prefix frontend
npm test --prefix frontend
```

A separate clean frontend copy passed `npm ci`, the production build and the earlier three frontend render/asset tests (the current suite has five, including view separation and face-box geometry) on Node.js 22. The resulting local assets are about 149 KB JavaScript and 12 KB CSS compressed; no CDN, web fonts or third-party image hosts are needed by the UI. Backend tests remain separate.

The in-app browser was used to start a real Gemma review of 18 unaltered KonIQ quality-evaluation images: all 18 were reviewed, six picked, and 12,099 local tokens reported. All 18 original hashes and all six ZIP members were checked against source bytes; a separate watermarked JPEG retained the supplied Artist credit and omitted inherited GPS. The AI picked two images from the low-human-quality group. This reveals a quality-calibration gap, not a passing accuracy benchmark; KonIQ quality ratings also do not measure event storytelling.

The local event demo uses a separate set of public [Wikimedia Hackathon Kochi 2024 photos](https://commons.wikimedia.org/wiki/Category:Wikimedia_Hackathon_Kochi_2024), with per-photo author, license, source page and hash retained in ignored local dataset metadata. Neither demo photos nor local event data are part of the contribution. The earlier eight-photo public event run reviewed all eight, picked four, and used 4,673 local tokens. An identical review started from the browser reused eight cached scores and used zero new tokens. All eight source hashes and the four ZIP members were verified.

## Known Limitations

- Local laptop pilot, not secure multi-user hosting: no accounts, remote sharing, per-user authorization, upload moderation or production storage. It binds to 127.0.0.1 only.
- The dark React/beUI UI is a local pilot. Native file-picker automation, mobile-device interaction, and browser-native sharing have not been verified.
- Event face search is approximate. Lighting, angle, face size and image quality affect results; thresholds are not probabilities. No identity database, face naming or sensitive-trait inference is used. Event embeddings are stored locally after an opt-in search and can be cleared.
- Thumbnail/model previews can hide fine expressions and small faces. SFace does not guarantee equal accuracy across populations. Review results before sharing.
- Local AI quality and speed depend on the exact model/hardware. Subjective ratings and captions can be wrong. No automatic publication occurs. Eight-GB-laptop performance and larger-model benefits have not been established.
- Blur/exposure are imperfect: bokeh, intentional motion, high-key/low-key lighting and sharp backgrounds can mislead technical hints. AI still reviews these frames.
- pHash grouping is O(n²) and transitive, not capture-time burst analysis or full semantic scene clustering. Diversity preference can be imperfect; every frame stays available and unused slots can include same-group frames.
- CLI scans one directory non-recursively and skips symlinks. Web imports copy file bytes into local event storage. Unsupported/corrupt files are reported, not repaired.
- Original copies retain EXIF/GPS. JPEG derivatives strip inherited metadata and optionally add photographer credit. A supplied photographer name/watermark is attribution, not proof of authorship. RAF derivatives use the camera's JPEG, not full RAW development.
- No real RAF camera file has been validated. Browser native photo sharing is browser/OS-dependent; downloading plus copying the caption remains available.
- Cached scores contain subjective judgments; replacing weights under the same model tag needs cache clearing. Version ranges are bounded rather than lockfile-pinned for Python; frontend npm has a lockfile.
- Current platform checks: macOS Python 3.12, with refreshed backend checks passing on Python 3.11 as well. Linux/Windows are unverified. See the latest test output for refreshed backend cross-version checks.

## Security & Privacy Considerations

- Loopback-only backend, strict local sessions, same-origin write checks, no public bind option or automatic cloud fallback.
- Upload permission and face-search consent are enforced server-side. File count/size, formats, pixel-decompression limits and decoding are validated. Filenames cannot select storage paths. Inputs never execute as code.
- One active AI review, bounded retries, finite time budget and cancellation checks. Invalid/mismatched AI results stop instead of inventing scores; previous web picks survive failure/cancellation.
- Original input files are never modified or deleted. CLI output must be separate/new/empty. Watermarking/metadata use separate copies; ZIP/report artifacts are local.
- References are processed in memory and discarded. Event face embeddings are private local data; clear them from the UI/API. The event directory is restricted to its owner.
- The optional Gemini path uploads metadata-free resized previews only when explicitly chosen. The default local path sends images only to loopback Ollama. Keep Ollama bound to loopback too.
- Contact sheets include previews of rejected photos and captions; protect them like originals. Source formats, `.env`, databases, caches and local galleries are ignored by Git. No personal photos or model weights are committed.
- CSV formula protection and HTML escaping cover untrusted filenames/model text. A local pilot is not a hardened public service; do not expose it through a tunnel as-is.

## Future Improvements

The backend and dark React/beUI interface have passed local checks. The next priority is improving editorial quality: the first 18-image KonIQ evaluation included two low-human-quality images among six AI picks. Future hosted deployment would need accounts, permissions, moderation, durable object storage and operational limits. Larger-model quality comparisons and indexed similarity lookup should follow measurement rather than become baseline requirements.

## License

Contributed under the repository's [MIT license](../../LICENSE). Vendored beUI source retains its [MIT notice](frontend/LICENSE.beui) and [registry provenance](frontend/BEUI-SOURCES.json). Face weights are downloaded separately from [OpenCV Zoo](https://github.com/opencv/opencv_zoo): YuNet is MIT, SFace is Apache-2.0. No model weights or event photographs are distributed. Gemma 4 is available under [Apache-2.0](https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/); respect the chosen runtime/model licenses.


### Current local agent verification

The current-event organizer demo imported 28 JPEGs from an explicitly supplied local directory with zero skipped files. A real organizer-chat request, `Photos with the Google logo`, made Gemma choose `visual_search`, inspect all 28 photos, and return six candidates in two planner turns, reporting 10,971 local tokens including visual tool work. This verifies end-to-end tool use and UI results, not a measured precision/recall score. A separate public-album query selected `count_faces` and returned seven multi-face photos out of eight. The Google-logo positive control also returned a positive decision.

The compact interface uses beUI TodoList for processing, PromptInput for the floating organizer composer, and MessageBubble for the current reply. Previous replies are cleared when a new request starts, and dismissed replies are not restored after reload. Attendees have a separate photo-first view. All event photos, references, model weights and local results remain outside the contribution.

Final source-only clean-install check: all declared Python requirements installed into an empty Python 3.12 environment, all 73 tests passed, and the generated six-photo mock run produced two picks and CSV/HTML reports. Application Python/React/CSS files were formatted before the final build checks.

If Gemma omits its final narration after a successful tool call, the agent returns a deterministic summary and candidate count from the completed tool result. An empty response before any tool runs still fails; tool errors are not hidden. Regression coverage includes empty/whitespace/missing narration, zero and nonzero face-search results, and the full face-count API path.
