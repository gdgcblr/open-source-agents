import { defineTool } from "@grok/agent-sdk/tools";
import * as z from "zod/v4";
import { listBundledSourceFiles } from "../lib/bundled-sources.js";

export default defineTool({
  description:
    "List offline demo source files bundled with this agent (markdown under sandbox sources).",
  effect: "read",
  inputSchema: z.object({}),
  async execute() {
    const files = await listBundledSourceFiles();
    return { files, count: files.length };
  },
});
