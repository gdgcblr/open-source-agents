import {
  FunctionTool,
  InMemorySessionService,
  LlmAgent,
  Runner,
  type BaseLlm,
} from '@google/adk';
import { z } from 'zod';
import type { AgentLoggerPlugin } from '../src/adk.js';
import { describeFailure } from '../src/adk-failures.js';

/** A sanitized demo failure; its message contains no original provider payload. */
export class ExampleRunError extends Error {}

/** Args: plugin, model and failure switch. Returns: visible answer. Raises: safe error on provider failure or empty output. */
export async function runExample(
  plugin: AgentLoggerPlugin,
  model: BaseLlm | string,
  failTool = false,
): Promise<string> {
  const tool = new FunctionTool({
    name: 'get_weather',
    description: 'Returns fixture weather for a city; does not call a weather API.',
    parameters: z.object({ city: z.string().min(1).max(100) }),
    execute: ({ city }) => {
      if (failTool) throw new Error('Weather service unavailable');
      return { city, temperatureCelsius: 25, condition: 'clear' };
    },
  });
  const agent = new LlmAgent({
    name: 'weather_assistant',
    model,
    instruction:
      'Use get_weather to answer the user. Report that the weather is fixture data.',
    tools: [tool],
  });
  const runner = new Runner({
    appName: 'agent_logger_demo',
    agent,
    sessionService: new InMemorySessionService(),
    plugins: [plugin],
    autoCreateSession: true,
  });
  let answer = '';
  for await (const event of runner.runAsync({
    userId: 'demo',
    sessionId: 'demo',
    runConfig: { maxLlmCalls: 4 },
    abortSignal: AbortSignal.timeout(60_000),
    newMessage: { role: 'user', parts: [{ text: 'What is the weather in Bengaluru?' }] },
  })) {
    if (event.errorCode) throw new ExampleRunError(describeFailure(event).errorMessage);
    for (const part of event.content?.parts ?? []) {
      if (part.text && !part.thought) answer += part.text;
    }
  }
  if (!answer.trim())
    throw new ExampleRunError(
      'The agent finished without a visible answer. Inspect the log for model failures.',
    );
  return answer;
}
