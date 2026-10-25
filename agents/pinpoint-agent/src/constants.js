// All limits and defaults live here. Change a value here, nowhere else.

export const MODEL_NAME_DEFAULT = 'gemini-2.5-flash';
export const MAX_INPUT_CHARS = 8000;
export const MAX_TOOL_RESULT_CHARS = 8000;
export const DEFAULT_MAX_TOOL_CALLS = 6;
export const MAX_TOOL_CALLS_LIMIT = 20;
export const TRUNCATION_MARKER = '…[truncated]';
export const TOOL_CALL_CAP_REPLY = 'I reached the tool-call limit for this turn, so I stopped here. Try a smaller request.';

/** Tools the model may call. record_message and start_session are agent-only (D-3). */
export const MODEL_TOOL_ALLOWLIST = Object.freeze([
  'pin_message',
  'bookmark_message',
  'list_pins',
  'search_pins',
  'navigate_to_pin',
  'update_pin',
  'unpin',
  'list_sessions',
  'health',
  'export_pins',
  'import_pins',
]);

/** Tools that change or remove data. The REPL asks before running them (T-AG-6). */
export const DESTRUCTIVE_TOOLS = Object.freeze(['unpin']);

export const SERVER_RELATIVE_PATH = '../../tools/pinpoint-mcp-server/src/index.js';
export const E2E_TIMEOUT_MS = 30000;
export const LOG_LEVEL_DEFAULT = 'info';
export const LOG_LEVELS = Object.freeze(['debug', 'info', 'warn', 'error']);
