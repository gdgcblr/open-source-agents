import { createAgentLogger } from '../src/index.js';
import { AgentLoggerPlugin } from '../src/adk.js';
import { runExample } from './agent.js';
import { OfflineModel } from './offline-model.js';

const logger = await createAgentLogger();
const plugin = new AgentLoggerPlugin(logger);
try {
  console.log(await runExample(plugin, new OfflineModel()));
} finally {
  const status = await plugin.close();
  console.log(`Log: ${logger.filePath}`);
  console.log(`Delivery: ${JSON.stringify(status)}`);
  if (!status.success) process.exitCode = 1;
}
