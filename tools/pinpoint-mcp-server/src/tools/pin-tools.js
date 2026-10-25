// Pin tools: pin_message, bookmark_message, update_pin, unpin.
// pin and bookmark share one core. Re-pinning the same message returns the existing pin.

import {
  MAX_LABEL_CHARS,
  MAX_NOTE_CHARS,
  MAX_PINS_PER_SESSION,
  MAX_TAG_CHARS,
  MAX_TAGS,
  ORDER_STEP,
} from '../constants.js';
import { selectMessage } from '../identity.js';
import { newId } from '../ids.js';
import { StoreError } from '../store.js';
import { clampText } from '../text.js';
import {
  DESTRUCTIVE,
  ToolError,
  WRITE,
  findPin,
  makeSnippet,
  pickSelector,
  pinIdField,
  requireTrimmed,
  selectorShape,
  sessionIdField,
  summarisePin,
  unwrap,
  wrapTool,
  z,
} from './common.js';

const tagsField = z.array(z.string().max(MAX_TAG_CHARS)).max(MAX_TAGS).optional().describe('Up to 10 tags');

const cleanTags = (tags) => tags.map((t) => clampText(t.trim(), MAX_TAG_CHARS)).filter((t) => t.length > 0);

const nextOrder = (pins) => pins.reduce((max, p) => Math.max(max, p.order), 0) + ORDER_STEP;

function buildPin({ message, kind, label, note, tags, order, now }) {
  return {
    pinId: newId('p', now),
    kind,
    messageId: message.messageId,
    targetHash: message.textHash,
    role: message.role,
    snippet: makeSnippet(message.text),
    textLength: message.textLength,
    ordinal: message.ordinal,
    label,
    note,
    tags,
    order,
    createdAt: now,
    updatedAt: now,
    repairCount: 0,
  };
}

/** Locate a pin inside a mutable draft. Returns the live object so callers can edit it. */
function findPinInDraft(draft, pinId) {
  for (const session of Object.values(draft.sessions)) {
    const pin = session.pins.find((p) => p.pinId === pinId);
    if (pin) return { pin, session };
  }
  return null;
}

/** Resolve the selector against the current snapshot, then add the pin atomically. */
async function pinSelected(deps, args, { kind, label, note, tags, ctx }) {
  const { store, clock } = deps;
  ctx.sessionId = args.sessionId;
  const session = store.snapshot().sessions[args.sessionId];
  if (!session) throw new ToolError('SESSION_NOT_FOUND', 'no such session');

  const picked = selectMessage(session, pickSelector(args));
  if (picked.error) {
    const extra = picked.error.candidates ? { candidates: picked.error.candidates } : {};
    throw new ToolError(picked.error.code, picked.error.message, extra);
  }
  const { message } = picked;
  const existing = session.pins.find((p) => p.messageId === message.messageId);
  const promotes = kind === 'bookmark' && existing?.kind === 'pin';
  if (existing && !promotes) return { pin: summarisePin(existing, args.sessionId), alreadyPinned: true };

  const value = unwrap(
    await store.mutate((draft) => {
      const target = draft.sessions[args.sessionId];
      if (!target) throw new StoreError('SESSION_NOT_FOUND', 'no such session');
      const duplicate = target.pins.find((p) => p.messageId === message.messageId);
      if (duplicate && kind === 'bookmark' && duplicate.kind === 'pin') {
        // Bookmarking a pinned message promotes that pin in place: same pinId, new label.
        duplicate.kind = 'bookmark';
        duplicate.label = label;
        if (note) duplicate.note = note;
        if (tags.length > 0) duplicate.tags = tags;
        duplicate.updatedAt = clock();
        target.updatedAt = duplicate.updatedAt;
        return { pin: duplicate, alreadyPinned: true, promoted: true };
      }
      if (duplicate) return { pin: duplicate, alreadyPinned: true, promoted: false };
      if (target.pins.length >= MAX_PINS_PER_SESSION) {
        throw new StoreError('LIMIT_PINS', `pin limit of ${MAX_PINS_PER_SESSION} reached`);
      }
      const now = clock();
      const pin = buildPin({ message, kind, label, note, tags, order: nextOrder(target.pins), now });
      target.pins.push(pin);
      target.updatedAt = now;
      return { pin, alreadyPinned: false };
    }),
  );
  return { pin: summarisePin(value.pin, args.sessionId), alreadyPinned: value.alreadyPinned, promoted: value.promoted === true };
}

function registerPin(server, deps) {
  server.registerTool(
    'pin_message',
    {
      title: 'Pin message',
      description:
        'Pin one message in a session. Select it with exactly one of messageId, ordinal, last, or textQuery. Pinning an already-pinned message returns the existing pin.',
      inputSchema: {
        sessionId: sessionIdField,
        ...selectorShape,
        label: z.string().max(MAX_LABEL_CHARS).optional().describe('Optional label'),
        note: z.string().max(MAX_NOTE_CHARS).optional().describe('Optional note'),
        tags: tagsField,
      },
      annotations: { ...WRITE, title: 'Pin message' },
    },
    wrapTool('pin_message', deps, async (args, ctx) =>
      pinSelected(deps, args, {
        kind: 'pin',
        label: args.label ? clampText(args.label.trim(), MAX_LABEL_CHARS) || null : null,
        note: args.note ? clampText(args.note, MAX_NOTE_CHARS) : null,
        tags: cleanTags(args.tags ?? []),
        ctx,
      }),
    ),
  );

  server.registerTool(
    'bookmark_message',
    {
      title: 'Bookmark message',
      description: 'Bookmark one message with a required label. Same selector rules as pin_message.',
      inputSchema: {
        sessionId: sessionIdField,
        ...selectorShape,
        label: z.string().max(MAX_LABEL_CHARS).describe('Required label, for example "jwt-basics"'),
        note: z.string().max(MAX_NOTE_CHARS).optional().describe('Optional note'),
        tags: tagsField,
      },
      annotations: { ...WRITE, title: 'Bookmark message' },
    },
    wrapTool('bookmark_message', deps, async (args, ctx) => {
      const label = clampText(requireTrimmed(args.label, 'INVALID_INPUT', 'bookmark requires a non-empty label'), MAX_LABEL_CHARS);
      return pinSelected(deps, args, {
        kind: 'bookmark',
        label,
        note: args.note ? clampText(args.note, MAX_NOTE_CHARS) : null,
        tags: cleanTags(args.tags ?? []),
        ctx,
      });
    }),
  );
}

function registerEdit(server, deps) {
  server.registerTool(
    'update_pin',
    {
      title: 'Update pin',
      description: 'Change a pin label, note, or tags. Pass an empty label or note to clear it. Bookmarks keep a label.',
      inputSchema: {
        pinId: pinIdField,
        label: z.string().max(MAX_LABEL_CHARS).optional(),
        note: z.string().max(MAX_NOTE_CHARS).optional(),
        tags: tagsField,
      },
      annotations: { ...WRITE, title: 'Update pin' },
    },
    wrapTool('update_pin', deps, async (args, ctx) => {
      if (args.label === undefined && args.note === undefined && args.tags === undefined) {
        throw new ToolError('INVALID_INPUT', 'provide at least one of label, note, tags');
      }
      const { store, clock } = deps;
      const value = unwrap(
        await store.mutate((draft) => {
          const found = findPinInDraft(draft, args.pinId);
          if (!found) throw new StoreError('NOT_FOUND', 'no pin with that id');
          const { pin, session } = found;
          if (args.label !== undefined) pin.label = clampText(args.label.trim(), MAX_LABEL_CHARS) || null;
          if (pin.kind === 'bookmark' && !pin.label) throw new StoreError('INVALID_INPUT', 'bookmark requires a label');
          if (args.note !== undefined) pin.note = clampText(args.note, MAX_NOTE_CHARS) || null;
          if (args.tags !== undefined) pin.tags = cleanTags(args.tags);
          pin.updatedAt = clock();
          session.updatedAt = pin.updatedAt;
          return { pin, sessionId: session.sessionId };
        }),
      );
      ctx.sessionId = value.sessionId;
      return { pin: summarisePin(value.pin, value.sessionId) };
    }),
  );

  server.registerTool(
    'unpin',
    {
      title: 'Unpin',
      description: 'Remove a pin. Requires confirm: true. The message itself is not deleted.',
      inputSchema: {
        pinId: pinIdField,
        confirm: z.boolean().optional().describe('Must be true to remove the pin'),
      },
      annotations: { ...DESTRUCTIVE, title: 'Unpin' },
    },
    wrapTool('unpin', deps, async (args, ctx) => {
      if (args.confirm !== true) {
        throw new ToolError('CONFIRMATION_REQUIRED', 'unpin removes a pin; pass confirm: true to proceed');
      }
      const found = findPin(deps.store.snapshot(), args.pinId);
      if (!found) throw new ToolError('NOT_FOUND', 'no pin with that id');
      ctx.sessionId = found.session.sessionId;
      unwrap(
        await deps.store.mutate((draft) => {
          const target = findPinInDraft(draft, args.pinId);
          if (!target) throw new StoreError('NOT_FOUND', 'no pin with that id');
          target.session.pins = target.session.pins.filter((p) => p.pinId !== args.pinId);
          target.session.updatedAt = deps.clock();
          return true;
        }),
      );
      return { pinId: args.pinId, removed: true };
    }),
  );
}

export function register(server, deps) {
  registerPin(server, deps);
  registerEdit(server, deps);
}
