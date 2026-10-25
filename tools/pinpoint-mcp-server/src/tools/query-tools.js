// Query tools: list_pins, search_pins, navigate_to_pin, health.
// Read-only except navigate_to_pin, which persists identity repairs (fuzzy recovery) and
// never removes a pin when the target cannot be found (R6).

import {
  DEFAULT_CONTEXT_WINDOW,
  DEFAULT_LIST_LIMIT,
  MAX_CONTEXT_WINDOW,
  MAX_LABEL_CHARS,
  MAX_LIST_LIMIT,
  MAX_PINS_PER_SESSION,
  MAX_QUERY_CHARS,
  MAX_SESSIONS,
  MAX_MESSAGES_PER_SESSION,
  MAX_TAG_CHARS,
} from '../constants.js';
import { untrusted } from '../guardrails.js';
import { resolvePinTarget } from '../identity.js';
import { searchPins } from '../search.js';
import { StoreError } from '../store.js';
import { READ_ONLY, ToolError, WRITE, findPin, summarisePin, sessionIdField, wrapTool, z } from './common.js';

const pinIdParam = z.string().min(1).describe('Pin id returned by pin_message or bookmark_message');

function collectPins(snapshot, sessionId) {
  let sessions = Object.values(snapshot.sessions);
  if (sessionId !== undefined) {
    const one = snapshot.sessions[sessionId];
    if (!one) throw new ToolError('SESSION_NOT_FOUND', 'no such session');
    sessions = [one];
  }
  return sessions.flatMap((session) => session.pins.map((pin) => ({ pin, sessionId: session.sessionId })));
}

function registerList(server, deps) {
  server.registerTool(
    'list_pins',
    {
      title: 'List pins',
      description: 'List pins, most recent first. Filter by sessionId, kind (pin or bookmark), or tag.',
      inputSchema: {
        sessionId: sessionIdField.optional(),
        kind: z.enum(['pin', 'bookmark']).optional(),
        tag: z.string().max(MAX_TAG_CHARS).optional(),
        limit: z.number().int().min(1).max(MAX_LIST_LIMIT).optional().describe('Default 20, max 100'),
      },
      annotations: { ...READ_ONLY, title: 'List pins' },
    },
    wrapTool('list_pins', deps, async (args, ctx) => {
      ctx.sessionId = args.sessionId ?? null;
      let rows = collectPins(deps.store.snapshot(), args.sessionId);
      if (args.kind) rows = rows.filter((row) => row.pin.kind === args.kind);
      if (args.tag) rows = rows.filter((row) => row.pin.tags.includes(args.tag));
      rows.sort((a, b) => b.pin.createdAt - a.pin.createdAt);
      const limit = args.limit ?? DEFAULT_LIST_LIMIT;
      const pins = rows.slice(0, limit).map((row) => summarisePin(row.pin, row.sessionId));
      return { pins, count: rows.length, returned: pins.length };
    }),
  );
}

function registerSearch(server, deps) {
  server.registerTool(
    'search_pins',
    {
      title: 'Search pins',
      description: 'Search pins by keyword and fuzzy similarity over label, tags, note, and snippet. Low scores are dropped.',
      inputSchema: {
        query: z.string().min(1).max(MAX_QUERY_CHARS).describe('Search text'),
        sessionId: sessionIdField.optional(),
        limit: z.number().int().min(1).max(MAX_LIST_LIMIT).optional().describe('Default 20, max 100'),
      },
      annotations: { ...READ_ONLY, title: 'Search pins' },
    },
    wrapTool('search_pins', deps, async (args, ctx) => {
      ctx.sessionId = args.sessionId ?? null;
      const rows = collectPins(deps.store.snapshot(), args.sessionId);
      const sessionOf = new Map(rows.map((row) => [row.pin.pinId, row.sessionId]));
      const ranked = searchPins(
        rows.map((row) => row.pin),
        args.query,
        args.limit ?? DEFAULT_LIST_LIMIT,
      );
      const matches = ranked.map((hit) => ({
        ...summarisePin(hit.pin, sessionOf.get(hit.pin.pinId)),
        score: hit.score,
        matchedOn: hit.matchedOn,
      }));
      return { matches, count: matches.length };
    }),
  );
}

/** Persist a fuzzy identity repair. A failure here does not block navigation. */
async function persistRepair(deps, pinId, repair, now) {
  const result = await deps.store.mutate((draft) => {
    for (const session of Object.values(draft.sessions)) {
      const pin = session.pins.find((p) => p.pinId === pinId);
      if (pin) {
        pin.messageId = repair.messageId;
        pin.targetHash = repair.targetHash;
        pin.repairCount += 1;
        pin.updatedAt = now;
        return true;
      }
    }
    throw new StoreError('NOT_FOUND', 'no pin with that id');
  });
  if (!result.ok) deps.logger.warn('identity repair not persisted', { code: result.error.code });
}

function buildNavigation(session, target, before, after) {
  const index = session.messages.findIndex((m) => m.messageId === target.messageId);
  const start = Math.max(0, index - before);
  const end = Math.min(session.messages.length, index + after + 1);
  return {
    position: `message ${target.ordinal + 1} of ${session.messages.length}`,
    target: { messageId: target.messageId, ordinal: target.ordinal, role: target.role, untrustedContent: untrusted(target.text) },
    context: session.messages.slice(start, end).map((m) => ({
      ordinal: m.ordinal,
      role: m.role,
      isTarget: m.messageId === target.messageId,
      untrustedContent: untrusted(m.text),
    })),
  };
}

function registerNavigate(server, deps) {
  server.registerTool(
    'navigate_to_pin',
    {
      title: 'Navigate to pin',
      description:
        'Return the message a pin points to, its position in the session, and a context window of nearby messages. A pin whose message cannot be found is kept and reported as method not_found.',
      inputSchema: {
        pin: pinIdParam,
        contextBefore: z.number().int().min(0).max(MAX_CONTEXT_WINDOW).optional().describe('Messages before the target (0-10, default 2)'),
        contextAfter: z.number().int().min(0).max(MAX_CONTEXT_WINDOW).optional().describe('Messages after the target (0-10, default 2)'),
      },
      annotations: { ...WRITE, title: 'Navigate to pin' },
    },
    wrapTool('navigate_to_pin', deps, async (args, ctx) => {
      const found = findPin(deps.store.snapshot(), args.pin);
      if (!found) throw new ToolError('NOT_FOUND', 'no pin with that id');
      const sessionId = found.session.sessionId;
      ctx.sessionId = sessionId;
      const resolved = resolvePinTarget(found.session, found.pin);
      const now = deps.clock();
      let pin = found.pin;
      if (resolved.repair) {
        await persistRepair(deps, args.pin, resolved.repair, now);
        pin = { ...pin, messageId: resolved.repair.messageId, targetHash: resolved.repair.targetHash, repairCount: pin.repairCount + 1 };
      }
      if (!resolved.message) {
        return { pin: summarisePin(pin, sessionId), method: resolved.method, position: null, target: null, context: [] };
      }
      const before = args.contextBefore ?? DEFAULT_CONTEXT_WINDOW;
      const after = args.contextAfter ?? DEFAULT_CONTEXT_WINDOW;
      return {
        pin: summarisePin(pin, sessionId),
        method: resolved.method,
        ...buildNavigation(found.session, resolved.message, before, after),
      };
    }),
  );
}

function registerHealth(server, deps) {
  server.registerTool(
    'health',
    {
      title: 'Health',
      description: 'Report store counts, the last corruption event, quarantine count, and redaction and audit state. Never returns message text.',
      inputSchema: {},
      annotations: { ...READ_ONLY, title: 'Health' },
    },
    wrapTool('health', deps, async () => {
      const snapshot = deps.store.snapshot();
      const sessions = Object.values(snapshot.sessions);
      const h = deps.store.health();
      return {
        counts: {
          sessions: sessions.length,
          messages: sessions.reduce((n, s) => n + s.messages.length, 0),
          pins: sessions.reduce((n, s) => n + s.pins.length, 0),
        },
        lastCorruptionEvent: h.lastCorruptionEvent,
        quarantined: h.quarantined,
        redaction: deps.config.redact,
        audit: deps.config.audit,
        limits: {
          maxSessions: MAX_SESSIONS,
          maxMessagesPerSession: MAX_MESSAGES_PER_SESSION,
          maxPinsPerSession: MAX_PINS_PER_SESSION,
          maxLabelChars: MAX_LABEL_CHARS,
        },
      };
    }),
  );
}

export function register(server, deps) {
  registerList(server, deps);
  registerSearch(server, deps);
  registerNavigate(server, deps);
  registerHealth(server, deps);
}
