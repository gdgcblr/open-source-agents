// Transfer tools: export_pins, import_pins. Paths are confined to DATA_DIR/exports and
// DATA_DIR/imports (G6). Replace needs confirm: true and always backs up the current store first.

import { DEFAULT_EXPORT_PREFIX, MAX_MESSAGES_PER_SESSION, MAX_PINS_PER_SESSION, MAX_SESSIONS } from '../constants.js';
import { StoreError } from '../store.js';
import { backupCurrent, buildBundle, parseBundle, readImport, writeExport } from '../transfer.js';
import { ToolError, WRITE, sessionIdField, unwrap, wrapTool, z } from './common.js';

const fileNameField = z
  .string()
  .min(1)
  .max(64)
  .describe('File name without a directory, for example "pins-jwt". Letters, digits, dot, dash, underscore.');

/** Merge or replace sessions inside a mutable draft. Throws typed limit errors; never drops records. */
function applyImport(draft, incoming, mode, now) {
  const summary = { mode, sessionsAdded: 0, sessionsMerged: 0, messagesAdded: 0, pinsAdded: 0 };
  if (mode === 'replace') draft.sessions = {};
  for (const session of incoming) {
    const existing = draft.sessions[session.sessionId];
    if (!existing) {
      if (Object.keys(draft.sessions).length >= MAX_SESSIONS) {
        throw new StoreError('LIMIT_SESSIONS', `session limit of ${MAX_SESSIONS} reached`);
      }
      draft.sessions[session.sessionId] = structuredClone(session);
      summary.sessionsAdded += 1;
      summary.messagesAdded += session.messages.length;
      summary.pinsAdded += session.pins.length;
      continue;
    }
    summary.sessionsMerged += 1;
    const knownMessages = new Set(existing.messages.map((m) => m.messageId));
    for (const message of session.messages) {
      if (knownMessages.has(message.messageId)) continue;
      if (existing.messages.length >= MAX_MESSAGES_PER_SESSION) {
        throw new StoreError('LIMIT_MESSAGES', `message limit of ${MAX_MESSAGES_PER_SESSION} reached`);
      }
      existing.messages.push({ ...structuredClone(message), ordinal: existing.messages.length });
      summary.messagesAdded += 1;
    }
    const knownPins = new Set(existing.pins.map((p) => p.pinId));
    for (const pin of session.pins) {
      if (knownPins.has(pin.pinId)) continue;
      if (existing.pins.length >= MAX_PINS_PER_SESSION) {
        throw new StoreError('LIMIT_PINS', `pin limit of ${MAX_PINS_PER_SESSION} reached`);
      }
      existing.pins.push(structuredClone(pin));
      summary.pinsAdded += 1;
    }
    existing.updatedAt = now;
  }
  return summary;
}

function registerExport(server, deps) {
  server.registerTool(
    'export_pins',
    {
      title: 'Export pins',
      description:
        'Write a JSON export bundle to the exports folder of the data directory. Pass sessionId to export one session, or omit it to export everything.',
      inputSchema: {
        sessionId: sessionIdField.optional(),
        fileName: fileNameField.optional(),
      },
      annotations: { ...WRITE, title: 'Export pins' },
    },
    wrapTool('export_pins', deps, async (args, ctx) => {
      ctx.sessionId = args.sessionId ?? null;
      const now = deps.clock();
      const { text, counts } = buildBundle(deps.store.snapshot(), { sessionId: args.sessionId, now });
      const written = writeExport(deps.config.dataDir, args.fileName ?? `${DEFAULT_EXPORT_PREFIX}-${now}`, text);
      return { path: written.path, bytes: written.bytes, counts };
    }),
  );
}

function registerImport(server, deps) {
  server.registerTool(
    'import_pins',
    {
      title: 'Import pins',
      description:
        'Import a pinpoint export bundle from the imports folder of the data directory. mode merge adds missing sessions, messages, and pins. mode replace discards current data and requires confirm: true; the current store is backed up first.',
      inputSchema: {
        fileName: fileNameField,
        mode: z.enum(['merge', 'replace']).optional().describe('Default merge'),
        confirm: z.boolean().optional().describe('Required true for mode replace'),
      },
      annotations: { destructiveHint: true, readOnlyHint: false, idempotentHint: false, openWorldHint: false, title: 'Import pins' },
    },
    wrapTool('import_pins', deps, async (args) => {
      const mode = args.mode ?? 'merge';
      if (mode === 'replace' && args.confirm !== true) {
        throw new ToolError('CONFIRMATION_REQUIRED', 'replace discards current data; pass confirm: true to proceed');
      }
      const text = readImport(deps.config.dataDir, args.fileName);
      const { sessions, rejected } = parseBundle(text);
      const now = deps.clock();
      let backup = null;
      if (mode === 'replace') {
        const snapshot = deps.store.snapshot();
        if (Object.keys(snapshot.sessions).length > 0) backup = backupCurrent(deps.config.dataDir, snapshot, now);
      }
      const summary = unwrap(await deps.store.mutate((draft) => applyImport(draft, sessions, mode, now)));
      if (rejected.length > 0) deps.store.quarantine(rejected);
      return { ...summary, quarantined: rejected.length, backup: backup?.path ?? null };
    }),
  );
}

export function register(server, deps) {
  registerExport(server, deps);
  registerImport(server, deps);
}
