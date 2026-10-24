import assert from "node:assert/strict";
import { test } from "node:test";
import { rootAgent } from "../src/adk-agent.js";

test("ADK root agent exposes the three read-only tools", () => {
  assert.equal(rootAgent.name, "issue_reproduction_assistant");
  const names = rootAgent.tools.map((tool) => (tool as { name: string }).name).sort();
  assert.deepEqual(names, ["file_history", "investigate_github_issue", "investigate_local_issue"]);
});
