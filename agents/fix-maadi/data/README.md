# Channel registry packs

`bengaluru_channels.json` is the starter pack, not part of the agent's decision logic. A contributor can add a registry for another city or civic domain and point the app at it with:

```bash
FIX_MAADI_CHANNEL_FILE=data/my-city_channels.json python fix_maadi.py --port 8000
```

Keep the top-level shape as `{ "city": "...", "categories": { ... } }`. Each category may define `authority`, `reason`, and an `options` list. Every option should include an official `source`, `source_title`, `last_verified`, `mode`, `needs`, and a clear scope. Only use public, source-backed routes; do not commit private numbers, secrets, or scraped contact lists.
