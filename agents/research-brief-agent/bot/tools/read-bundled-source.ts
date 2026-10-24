import { defineTool } from "@grok/agent-sdk/tools";
import * as z from "zod/v4";
import { readBundledSourceFile } from "../lib/bundled-sources.js";

export default defineTool({
  description:
    "Read a bundled markdown source by filename (from list_bundled_sources). Use for offline or reproducible research.",
  effect: "read",
  inputSchema: z.object({
    filename: z
      .string()
      .describe("Bundled file name, e.g. healthcare-edge.md"),
  }),
  async execute({ filename }) {
    return readBundledSourceFile(filename);
  },
});
