import "dotenv/config";
import { InMemoryRunner, isFinalResponse, stringifyContent } from "@google/adk";
import { rootAgent } from "./adk-agent.js";

async function main(): Promise<void> {
  const prompt = process.argv.slice(2).join(" ").trim();
  if (!prompt) {
    console.error('Usage: npm run adk -- "Triage owner/repo#123"\n   or: npm run adk -- "Triage this bug: <text> in repo /abs/path"');
    process.exitCode = 1;
    return;
  }

  const runner = new InMemoryRunner({ agent: rootAgent, appName: "issue-reproduction-assistant" });
  const session = await runner.sessionService.createSession({ appName: runner.appName, userId: "cli" });
  console.error("Note: the ADK agent sends tool results (issue text, code excerpts) to Gemini to write the brief.");

  for await (const event of runner.runAsync({
    userId: "cli",
    sessionId: session.id,
    newMessage: { role: "user", parts: [{ text: prompt }] },
  })) {
    if (isFinalResponse(event)) {
      console.log(stringifyContent(event));
    }
  }
}

main().catch((error: unknown) => {
  console.error(`Error: ${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 1;
});
