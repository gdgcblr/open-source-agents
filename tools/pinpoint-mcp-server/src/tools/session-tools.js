// Session tools: start_session, record_message, list_sessions.
// record_message is the only way text enters the store: redaction and injection flagging run first.

import { MAX_MESSAGE_CHARS, MAX_TITLE_CHARS } from '../constants.js';
import { flagInjection, redactSecrets, stripControlChars } from '../guardrails.js';
import { clampText, fnvHex, normaliseForHash } from '../text.js';
import { ToolError, READ_ONLY, WRITE, sessionIdField, sessionTitle, unwrap, wrapTool, z } from './common.js';

export function register(server, deps) {
  const { store, config } = deps;

  server.registerTool(
    'start_session',
    {
      title: 'Start session',
      description: 'Start a new conversation session. Returns a sessionId to record messages into.',
      inputSchema: {
        title: z.string().max(MAX_TITLE_CHARS).optional().describe('Optional short title for the session'),
      },
      annotations: { ...WRITE, title: 'Start session' },
    },
    wrapTool('start_session', deps, async (args, ctx) => {
      const sessionId = unwrap(await store.createSession(args.title));
      ctx.sessionId = sessionId;
      return { sessionId };
    }),
  );

  server.registerTool(
    'record_message',
    {
      title: 'Record message',
      description:
        'Record one conversation turn into a session. Secrets are redacted before storage and prompt-injection phrases are flagged, not blocked.',
      inputSchema: {
        sessionId: sessionIdField,
        role: z.enum(['user', 'assistant', 'tool', 'unknown']).describe('Who wrote the message'),
        text: z.string().describe('Message text'),
      },
      annotations: { ...WRITE, title: 'Record message' },
    },
    wrapTool('record_message', deps, async (args, ctx) => {
      ctx.sessionId = args.sessionId;
      const cleaned = stripControlChars(args.text ?? '');
      if (cleaned.trim().length === 0) throw new ToolError('INVALID_INPUT', 'text must not be empty');
      const truncated = cleaned.length > MAX_MESSAGE_CHARS;
      const bounded = clampText(cleaned, MAX_MESSAGE_CHARS);
      const redaction = config.redact
        ? redactSecrets(bounded)
        : { text: bounded, redacted: false, types: [] };
      const suspicious = flagInjection(redaction.text);
      const message = unwrap(
        await store.appendMessage(args.sessionId, {
          role: args.role,
          text: redaction.text,
          textHash: fnvHex(normaliseForHash(redaction.text)),
          textLength: redaction.text.length,
          redacted: redaction.redacted,
          suspicious,
        }),
      );
      ctx.redacted = redaction.redacted;
      ctx.suspicious = suspicious;
      return {
        messageId: message.messageId,
        ordinal: message.ordinal,
        redacted: redaction.redacted,
        redactionTypes: redaction.types,
        suspicious,
        truncated,
      };
    }),
  );

  server.registerTool(
    'list_sessions',
    {
      title: 'List sessions',
      description: 'List sessions, most recently updated first, with message and pin counts.',
      inputSchema: {
        limit: z.number().int().min(1).max(100).optional().describe('Maximum sessions to return (default 20)'),
      },
      annotations: { ...READ_ONLY, title: 'List sessions' },
    },
    wrapTool('list_sessions', deps, async (args) => {
      const limit = args.limit ?? 20;
      const sessions = Object.values(store.snapshot().sessions)
        .sort((a, b) => b.updatedAt - a.updatedAt)
        .slice(0, limit)
        .map((s) => ({
          sessionId: s.sessionId,
          title: sessionTitle(s.title),
          createdAt: s.createdAt,
          updatedAt: s.updatedAt,
          messageCount: s.messages.length,
          pinCount: s.pins.length,
        }));
      return { sessions, count: sessions.length };
    }),
  );
}
