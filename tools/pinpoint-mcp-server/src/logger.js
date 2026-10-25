// Logger writes to stderr only (G10). stdout is reserved for the MCP protocol.

const LEVELS = { debug: 10, info: 20, warn: 30, error: 40 };

/**
 * @param {string} level  configured minimum level
 * @param {NodeJS.WritableStream} [stream]  defaults to process.stderr (overridable in tests)
 */
export function createLogger(level = 'info', stream = process.stderr) {
  const min = LEVELS[level] ?? LEVELS.info;
  const emit = (name, message, fields) => {
    if (LEVELS[name] < min) return;
    const line = JSON.stringify({ ts: new Date().toISOString(), level: name, message, ...fields });
    stream.write(`${line}\n`);
  };
  return {
    debug: (message, fields = {}) => emit('debug', message, fields),
    info: (message, fields = {}) => emit('info', message, fields),
    warn: (message, fields = {}) => emit('warn', message, fields),
    error: (message, fields = {}) => emit('error', message, fields),
  };
}
