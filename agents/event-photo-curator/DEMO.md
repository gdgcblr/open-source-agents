# Three-minute local demo

1. Open `/organizer` on the local server. Show the real event gallery and Import folder. Folder imports copy files without changing originals; duplicates are skipped.
2. Ask **Photos with the Google logo**. Show the beUI task list while Gemma chooses `visual_search`, then the candidate photos and response. Repeat the exact prompt to reuse cached image decisions; planning still uses local tokens.
3. Ask **Photos with multiple faces**. Show the task list reflecting face counting and the resulting photos. This detects/counts faces; it does not identify people.
4. Open one photo. Show its optimized preview, AI reason and untouched original download. Organizer-only JPEG exports can add a watermark and credit.
5. Switch to `/attendee`. Show the photo-first gallery and Find my photos. Only demonstrate live matching with consenting reference subjects; pair comparison expects exactly one face in each of two images. Dotted boxes show possible matches, amber indicates ambiguity.
6. Explain: Gemma 4 runs through Ollama; a custom Python tool loop chooses and executes tools and reads observations. Four-step limit, no shell or publishing tools, local caches and cooperative stop. Photo curation is a separate bounded pipeline.

## Run

```bash
python -m curator serve --data .cache/current-event
# http://127.0.0.1:8787/organizer
# http://127.0.0.1:8787/attendee
python -m curator ask 'Photos with the Google logo'
```

The `.cache/current-event` directory is private local state and is not distributed. Another user imports their own folder first. UI views are workflow separation, not authentication. No hosted deployment is required. Video publication is managed separately by the project owner.
