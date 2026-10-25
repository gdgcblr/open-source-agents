// stderr-only logger. stdout belongs to the chat UI.

const LEVELS = { debug: 10, info: 20, warn: 30, error: 40 };

export function createLogger(level = 'info', stream = process.stderr) {
  const min = LEVELS[level] ?? LEVELS.info;
  const emit = (name, message, fields = {}) => {
    if (LEVELS[name] < min) return;
    stream.write(`${JSON.stringify({ ts: new Date().toISOString(), level: name, message, ...fields })}\n`);
  };
  return {
    debug: (m, f) => emit('debug', m, f),
    info: (m, f) => emit('info', m, f),
    warn: (m, f) => emit('warn', m, f),
    error: (m, f) => emit('error', m, f),
  };
}
