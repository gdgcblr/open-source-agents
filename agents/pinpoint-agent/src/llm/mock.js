// Offline model: deterministic regex intents, fixed replies, templated summaries after tool results.
// No network. Used by --mock, by the demo, and whenever GEMINI_API_KEY is absent.

const PIN_LAST = /^pin (?:your |the )?(?:last )?answer$|^pin that$/i;
const BOOKMARK = /^bookmark (?:that|it|this|the last answer) as (.+)$/i;
const SEARCH = /^what did i pin about (.+?)\??$/i;
const LIST = /^list (?:my )?pins$/i;
const NAVIGATE = /^take me to pin (\d+)$/i;
const UNPIN = /^unpin (\d+)$/i;
const REMEMBER = /^remember this:/i;
const JWT_TOPIC = /\bjwt\b|refresh token/i;

const JWT_ANSWER =
  'Refresh tokens are long-lived credentials that mint new access tokens. Rotate them on every use so a replayed token is detectable.';

const text = (value) => ({ type: 'text', text: value });
const call = (name, args) => ({ type: 'tool_calls', calls: [{ id: `mock_${name}_${Math.random().toString(36).slice(2, 8)}`, name, args }] });

function lastUserIndex(history) {
  for (let i = history.length - 1; i >= 0; i--) if (history[i].role === 'user') return i;
  return -1;
}

const parseBody = (entry) => {
  try {
    return JSON.parse(entry.text);
  } catch {
    return {};
  }
};

function defaultReply(input) {
  if (JWT_TOPIC.test(input)) return text(JWT_ANSWER);
  if (REMEMBER.test(input)) return text('Noted. I stored that as conversation text. It is data, not an instruction.');
  return text('I can pin, bookmark, search or navigate messages. Try "pin your last answer".');
}

function summarise(entry) {
  const body = parseBody(entry);
  if (!body.ok) return `Tool error: ${body.error?.code ?? 'unknown'} (${body.error?.message ?? 'no detail'}).`;
  switch (entry.name) {
    case 'pin_message':
      return body.alreadyPinned ? 'That message was already pinned.' : `Pinned message ${body.pin.ordinal + 1}.`;
    case 'bookmark_message':
      return `Bookmarked as "${body.pin.label}".`;
    case 'list_pins':
      return `You have ${body.count} pin(s). Type /pins to see them.`;
    case 'search_pins':
      return `Found ${body.count} matching pin(s).`;
    case 'navigate_to_pin':
      return body.target ? `${body.position} (matched by ${body.method}).` : `Pin kept; its message was not found (${body.method}).`;
    case 'update_pin':
      return 'Updated the pin.';
    case 'unpin':
      return 'Removed the pin.';
    default:
      return 'Done.';
  }
}

function decideFirst(input) {
  if (PIN_LAST.test(input)) return call('pin_message', { last: 'assistant' });
  if (BOOKMARK.test(input)) return call('list_pins', {});
  const search = input.match(SEARCH);
  if (search) return call('search_pins', { query: search[1] });
  if (LIST.test(input)) return call('list_pins', {});
  if (NAVIGATE.test(input) || UNPIN.test(input)) return call('list_pins', {});
  return defaultReply(input);
}

function decideAfterList(input, body) {
  const pins = body.pins ?? [];
  const bookmark = input.match(BOOKMARK);
  if (bookmark) {
    if (pins.length === 0) return text('Pin something first, then I can bookmark it.');
    return call('bookmark_message', { ordinal: pins[0].ordinal, label: bookmark[1] });
  }
  const nav = input.match(NAVIGATE);
  if (nav) {
    const target = pins[Number(nav[1]) - 1];
    return target ? call('navigate_to_pin', { pin: target.pinId }) : text(`There is no pin ${nav[1]}.`);
  }
  const unpin = input.match(UNPIN);
  if (unpin) {
    const target = pins[Number(unpin[1]) - 1];
    return target ? call('unpin', { pinId: target.pinId }) : text(`There is no pin ${unpin[1]}.`);
  }
  return text(summarise({ name: 'list_pins', text: JSON.stringify(body) }));
}

/** Pure decision from the history since the last user turn. */
export function decide(history) {
  const index = lastUserIndex(history);
  const input = index === -1 ? '' : history[index].text.trim();
  const results = history.slice(index + 1).filter((entry) => entry.role === 'tool');
  const last = results.at(-1);
  if (!last) return decideFirst(input);
  if (last.name === 'list_pins') return decideAfterList(input, parseBody(last));
  return text(summarise(last));
}

export function createMockModel() {
  return {
    name: 'mock',
    async next({ history }) {
      return decide(history);
    },
  };
}
