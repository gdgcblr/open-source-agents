import { createAgentLogger } from '../src/index.js';
import { AgentLoggerPlugin } from '../src/adk.js';
import { ExampleRunError, runExample } from './agent.js';
import { describeFailure } from '../src/adk-failures.js';

if (!process.env.GOOGLE_API_KEY) throw new Error('Set GOOGLE_API_KEY in .env first.');
const logger = await createAgentLogger();
const plugin = new AgentLoggerPlugin(logger);
try {
  console.log(
    await runExample(plugin, process.env.GEMINI_MODEL ?? 'gemini-3.5-flash-lite'),
  );
} catch (error) {
  const message =
    error instanceof ExampleRunError
      ? error.message
      : describeFailure(error).errorMessage;
  console.error(`Agent run failed: ${message}`);
  process.exitCode = 1;
} finally {
  const status = await plugin.close();
  console.log(`Log: ${logger.filePath}`);
  console.log(`Delivery: ${JSON.stringify(status)}`);
  if (!status.success) {
    console.error('Log delivery incomplete:', status);
    process.exitCode = 1;
  }
}
