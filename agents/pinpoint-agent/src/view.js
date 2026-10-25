// Plain-text views for the terminal. Stored message text is shown as quoted data, never as commands.

const TARGET_MARK = '▶';

/** Text inside untrustedContent is the only place stored message text appears. */
const storedText = (wrapper) => (wrapper && typeof wrapper.text === 'string' ? wrapper.text : '');

export function formatPins(pins) {
  if (!pins || pins.length === 0) return ['No pins yet.'];
  return pins.map((pin, index) => {
    const label = pin.label ? ` "${pin.label}"` : '';
    return `  [${index + 1}] ${pin.kind}${label} (${pin.role}, message ${pin.ordinal + 1}) ${JSON.stringify(storedText(pin.untrustedContent))}`;
  });
}

/** Navigation view: the pinned message is marked with ▶. */
export function formatNavigation(nav) {
  if (!nav.target) return [`Pin kept. Its message was not found (matched by ${nav.method}).`];
  const lines = [`Pin points to ${nav.position} (matched by ${nav.method}):`];
  for (const item of nav.context ?? []) {
    const mark = item.isTarget ? TARGET_MARK : ' ';
    lines.push(`${mark} ${item.ordinal + 1}. ${item.role}: ${JSON.stringify(storedText(item.untrustedContent))}`);
  }
  return lines;
}

export const HELP_LINES = [
  'Commands: /pins  list pins    /help  this help    /exit  quit',
  'Try: "pin your last answer", "bookmark that as <label>", "what did I pin about <x>",',
  '     "take me to pin <N>", "unpin <N>" (asks first).',
];
