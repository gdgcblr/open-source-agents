import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createGeminiModel, toContents } from '../src/llm/gemini.js';

// Built at runtime so no key-shaped literal appears in source.
const KEY = ['AI', 'za'].join('') + 'FAKE'.repeat(8) + 'FAK';
const TOOLS = [{ name: 'list_pins', description: 'List pins', inputSchema: { type: 'object', properties: { limit: { type: 'number' } } } }];

function fakeClient({ response, fail = false } = {}) {
  const requests = [];
  return {
    requests,
    models: {
      async generateContent(request) {
        requests.push(request);
        if (fail) throw new Error(`rejected key ${KEY}`);
        return response ?? { functionCalls: undefined, text: 'hi' };
      },
    },
  };
}

test('T-AG-7: adapter sends functionDeclarations with the MCP schema and returns tool calls', async () => {
  const client = fakeClient({ response: { functionCalls: [{ name: 'list_pins', args: { limit: 3 } }] } });
  const model = createGeminiModel({ apiKey: KEY, modelName: 'test-model', client });
  const step = await model.next({ systemPrompt: 'sys', history: [{ role: 'user', text: 'list' }], tools: TOOLS });
  const request = client.requests[0];
  assert.equal(request.model, 'test-model');
  assert.equal(request.config.systemInstruction, 'sys');
  assert.deepEqual(request.config.tools[0].functionDeclarations[0].parametersJsonSchema, TOOLS[0].inputSchema);
  assert.equal(step.type, 'tool_calls');
  assert.equal(step.calls[0].name, 'list_pins');
  assert.deepEqual(step.calls[0].args, { limit: 3 });
});

test('T-AG-7b: text responses come back as text; tool results map to functionResponse parts', async () => {
  const client = fakeClient({ response: { text: 'plain answer' } });
  const model = createGeminiModel({ apiKey: KEY, modelName: 'm', client });
  assert.deepEqual(await model.next({ systemPrompt: '', history: [], tools: [] }), { type: 'text', text: 'plain answer' });
  const contents = toContents([{ role: 'tool', id: 'c1', name: 'list_pins', text: '{"ok":true}' }]);
  assert.deepEqual(contents[0].parts[0].functionResponse, { id: 'c1', name: 'list_pins', response: { result: '{"ok":true}' } });
});

test('T-AG-7c: a failed request never leaks the API key into the error', async () => {
  const client = fakeClient({ fail: true });
  const model = createGeminiModel({ apiKey: KEY, modelName: 'm', client });
  await assert.rejects(model.next({ systemPrompt: '', history: [], tools: [] }), (error) => {
    assert.match(error.message, /model request failed/);
    assert.equal(error.message.includes(KEY), false);
    return true;
  });
});
