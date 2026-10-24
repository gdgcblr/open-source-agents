# Local React interface

Dark React UI with vendored beui.dev buttons, inputs, TodoList, PromptInput, MessageBubble, AgentProgress and AgentActivity. Source provenance and MIT notice are in `BEUI-SOURCES.json` and `LICENSE.beui`. Unused registry demo components are omitted.

The production build lives in `../curator/static/` and ships with the Python project. The `/organizer` and `/attendee` paths provide distinct local workflows, not authenticated roles. Normal use needs no Node.js:

```bash
# From agents/event-photo-curator, with the Python environment active:
python -m curator serve
# Open http://127.0.0.1:8787
```

To edit the UI, use Node.js 20.19+ or 22.12+ (Node 22 tested), then from the project directory:

```bash
npm ci --prefix frontend
npm run build --prefix frontend
npm test --prefix frontend
```

`npm run dev --prefix frontend` watches and rebuilds assets. Keep the Python server running and manually reload the same localhost page. This preserves the backend's loopback sessions and origin checks; there is no separate frontend server or cloud deployment. Building replaces the generated static assets, never event data.

Frontend tests use Node's test runner, Vite's server-side module loader and React's HTML renderer. They cover safe photo text, picked/unpicked badges, photo details/export controls, and the production asset entry. They are not interactive browser tests. Manual in-app browser checks separately cover gallery/shortlist navigation, real Ollama review, details, watermark controls and Escape navigation. Upload bytes and download/export integrity are verified through the local API; file-picker interaction and browser-native sharing remain unverified.
