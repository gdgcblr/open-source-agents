import assert from 'node:assert/strict';
import { GoogleGenAI } from '@google/genai';
import { createAgentLogger, readLog, type AgentSpan } from '../src/index.js';
import { describeFailure } from '../src/adk-failures.js';
import { readRepositoryContext } from './repository-context.js';
import { runStoryAgent } from './story-agent.js';

if (!process.env.GOOGLE_API_KEY?.trim()) throw new Error('Set GOOGLE_API_KEY in .env.');
const logger = await createAgentLogger({ captureContent: true });
const client = new GoogleGenAI({ apiKey: process.env.GOOGLE_API_KEY });

async function generateStory(prompt: string, span: AgentSpan): Promise<string> {
  const response = await client.models.generateContent({
    model: process.env.GEMINI_MODEL ?? 'gemini-3.5-flash-lite',
    contents: prompt,
    config: { maxOutputTokens: 1024, httpOptions: { timeout: 30000 } },
  });
  span.recordUsage('gemini', response);
  return response.text ?? '';
}

try {
  const args = process.argv.slice(2);
  if (args.length && (args[0] !== '--repo' || args.length !== 2 || !args[1]))
    throw new Error('Usage: npm run demo:story -- [--repo ../your-project]');
  const readContext = logger.wrapTool(
    'repository.read_public_context',
    readRepositoryContext,
  );
  const context = args[1] ? await readContext(args[1]) : '';
  const result = await runStoryAgent(logger, generateStory, context);
  console.log(result.story);
  console.log(`Words: ${result.wordCount}`);
} catch (error) {
  console.error(`Story run failed: ${describeFailure(error).errorMessage}`);
  process.exitCode = 1;
} finally {
  const delivery = await logger.close();
  console.log(`Log: ${logger.filePath}`);
  console.log(`Delivery: ${JSON.stringify(delivery)}`);
  if (!delivery.success) process.exitCode = 1;
}
if (!process.exitCode && logger.filePath) {
  const events = await readLog(logger.filePath);
  assert.ok(events.some((event) => event.kind === 'model' && event.phase === 'finished'));
  assert.ok(
    events.some((event) => event.kind === 'tool' && event.status === 'completed'),
  );
  console.log(`Verified ${events.length} retained events.`);
}
