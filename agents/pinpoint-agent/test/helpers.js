// Test doubles: a stub MCP client that records calls, and scripted models.

export const SESSION_ID = 's_test_abc';

export const ALL_SERVER_TOOLS = [
  'start_session', 'record_message', 'pin_message', 'bookmark_message', 'list_pins', 'search_pins',
  'navigate_to_pin', 'update_pin', 'unpin', 'list_sessions', 'health', 'export_pins', 'import_pins',
];

export function stubMcp(replies = {}) {
  const calls = [];
  const tools = ALL_SERVER_TOOLS.map((name) => ({ name, description: `${name} tool`, inputSchema: { type: 'object', properties: {} } }));
  const defaults = { start_session: { ok: true, sessionId: SESSION_ID }, record_message: { ok: true }, list_pins: { ok: true, pins: [], count: 0 } };
  return {
    calls,
    tools,
    async listTools() {
      return tools;
    },
    async callTool(name, args) {
      calls.push({ name, args });
      const reply = replies[name] ?? defaults[name] ?? { ok: true };
      const body = typeof reply === 'function' ? reply(args) : reply;
      return { isError: body.ok === false, body, text: JSON.stringify(body) };
    },
    executed: (name) => calls.filter((c) => c.name === name),
  };
}

/** Model that returns the given steps in order, then plain text 'done'. */
export function scriptedModel(steps) {
  const seen = [];
  const queue = [...steps];
  return {
    name: 'scripted',
    seen,
    async next(request) {
      seen.push(request);
      return queue.length > 0 ? queue.shift() : { type: 'text', text: 'done' };
    },
  };
}

/** Model that always asks for the same tool call. Used for the call-cap test. */
export function alwaysCall(name, args) {
  let n = 0;
  return {
    name: 'always',
    async next() {
      n += 1;
      return { type: 'tool_calls', calls: [{ id: `c${n}`, name, args }] };
    },
  };
}
