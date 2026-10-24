import { defineEval, includes } from "@grok/agent-sdk/evals";

export default defineEval({
  tags: ["smoke"],
  description:
    "Produces a structured report from bundled healthcare-edge fixture source.",
  async test(t) {
    await t.send(
      'Using bundled sources only, research "edge computing in healthcare" from healthcare-edge.md and write a full structured research report.',
    );
    t.succeeded();
    t.calledTool("read_bundled_source");
    t.check(t.reply, includes("## Executive Summary"));
    t.check(t.reply, includes("## Evidence Table"));
    t.check(t.reply, includes("healthcare-edge.md"));
  },
});
