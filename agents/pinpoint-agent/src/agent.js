// Turn loop. The agent records every user and assistant turn itself (D-3); the model never
// sees record_message or start_session. Each model tool call goes through the allowlist, the
// session injection, the confirmation gate and the per-turn call budget.

import { TOOL_CALL_CAP_REPLY } from './constants.js';
import {
  clampInput,
  createToolBudget,
  injectSession,
  isAllowedTool,
  needsConfirmation,
  truncateResult,
  withConfirmation,
} from './guardrails.js';
import { SYSTEM_PROMPT } from './prompts.js';

const noopLogger = { debug() {}, info() {}, warn() {}, error() {} };

const errorText = (code, message) => JSON.stringify({ ok: false, error: { code, message } });

/**
 * @param {{ model, mcp, maxToolCalls: number, confirm: (req) => Promise<boolean>, logger? }} deps
 */
export function createAgent({ model, mcp, maxToolCalls, confirm, logger = noopLogger }) {
  let sessionId = null;
  let tools = [];
  const history = [];
  /** Names and outcomes only, never text. Used by the demo and tests. */
  const toolLog = [];

  async function init({ sessionId: existing } = {}) {
    tools = (await mcp.listTools()).filter((t) => isAllowedTool(t.name));
    if (existing) {
      sessionId = existing;
    } else {
      const started = await mcp.callTool('start_session', { title: 'pinpoint-agent' });
      if (!started.body.ok) throw new Error(`start_session failed: ${started.body.error?.code}`);
      sessionId = started.body.sessionId;
    }
    logger.info('session ready', { sessionId });
    return sessionId;
  }

  const record = (role, text) => mcp.callTool('record_message', { sessionId, role, text });

  async function runTool(call) {
    if (!isAllowedTool(call.name)) {
      toolLog.push({ name: call.name, ok: false });
      return { name: call.name, ok: false, text: errorText('TOOL_NOT_ALLOWED', 'this tool is not available to the model') };
    }
    const gated = needsConfirmation(call.name, call.args);
    let args = injectSession(call.args, sessionId);
    if (gated) {
      const approved = (await confirm({ name: call.name, args })) === true;
      if (!approved) {
        toolLog.push({ name: call.name, ok: false });
        return { name: call.name, ok: false, text: errorText('CONFIRMATION_DENIED', 'the user did not confirm') };
      }
      args = withConfirmation(args, true);
    } else {
      args = withConfirmation(args, false);
    }
    const result = await mcp.callTool(call.name, args);
    const ok = result.body.ok === true;
    toolLog.push({ name: call.name, ok });
    return { name: call.name, ok, text: truncateResult(result.text), navigation: result.body.position ? result.body : null };
  }

  /** Run one human turn. Returns { reply, navigation[], toolResults[] }. */
  async function turn(userText) {
    const clamp = clampInput(userText);
    await record('user', clamp.text);
    history.push({ role: 'user', text: clamp.text });

    const budget = createToolBudget(maxToolCalls);
    const navigation = [];
    const toolResults = [];
    let reply = null;

    while (reply === null) {
      const step = await model.next({ systemPrompt: SYSTEM_PROMPT, history, tools });
      if (step.type === 'text') {
        reply = step.text;
        break;
      }
      history.push({ role: 'model', calls: step.calls });
      let executed = 0;
      for (const call of step.calls) {
        if (!budget.take()) {
          history.push({ role: 'tool', id: call.id, name: call.name, text: errorText('CALL_LIMIT', 'tool-call limit reached') });
          continue;
        }
        executed += 1;
        const result = await runTool(call);
        toolResults.push({ name: result.name, ok: result.ok });
        if (result.navigation) navigation.push(result.navigation);
        history.push({ role: 'tool', id: call.id, name: call.name, text: result.text });
      }
      if (executed === 0) reply = TOOL_CALL_CAP_REPLY;
    }

    await record('assistant', reply);
    history.push({ role: 'assistant', text: reply });
    return { reply, navigation, toolResults };
  }

  async function listPins() {
    const result = await mcp.callTool('list_pins', { sessionId });
    return result.body;
  }

  return { init, turn, listPins, getSessionId: () => sessionId, toolLog };
}
