#!/usr/bin/env node
import "dotenv/config";
import { createA2AServer } from "./a2a-server.js";

const port = Number(process.env.A2A_PORT ?? 4747);
const allowUpload = process.env.A2A_ALLOW_UPLOAD === "1";
const server = createA2AServer({ port, allowUpload });

server.listen(port, "127.0.0.1", () => {
  console.error(`A2A agent listening on http://127.0.0.1:${port}/ (${allowUpload ? "model-assisted" : "offline"} mode)`);
  console.error(`Agent card: http://127.0.0.1:${port}/.well-known/agent-card.json`);
});
