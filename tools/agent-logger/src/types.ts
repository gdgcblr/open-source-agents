/** JSON-compatible, already-filtered log values. */
export type JsonValue =
  null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };
export const SPAN_KINDS = [
  'run',
  'agent',
  'model',
  'tool',
  'workflow',
  'retrieval',
  'embedding',
  'memory',
  'custom',
] as const;
export type SpanKind = (typeof SPAN_KINDS)[number];
export type SpanStatus = 'completed' | 'failed' | 'interrupted';

/** Versioned wire format. Sequence reflects logger receipt order, not causality. */
export interface LogEvent {
  readonly schemaVersion: 1;
  readonly sequence: number;
  readonly timestamp: string;
  readonly runId: string;
  readonly spanId: string;
  readonly parentSpanId?: string;
  readonly kind: SpanKind;
  readonly name: string;
  readonly phase: 'started' | 'finished';
  readonly status?: SpanStatus;
  readonly durationMs?: number;
  readonly data?: JsonValue;
}

/** Storage extension point. Receives sanitized events; must settle writes promptly. */
export interface LogSink {
  /** Args: event to persist. Returns: completion. Raises: on storage failure. */
  write(event: LogEvent): void | Promise<void>;
  /** Args: none. Returns: completion. Raises: on storage close failure. */
  close?(): void | Promise<void>;
}

/** Counters include all events attempted during this logger's lifetime. */
export interface DeliveryStatus {
  readonly success: boolean;
  readonly written: number;
  readonly failed: number;
  readonly dropped: number;
  readonly pending: number;
}

/** Defaults: metadata-only, .agent-logs, 256 pending events, 16 MiB per file. */
export interface AgentLoggerOptions {
  readonly directory?: string;
  readonly sink?: LogSink;
  readonly captureContent?: boolean;
  readonly maxPendingEvents?: number;
  readonly maxActiveSpans?: number;
  readonly maxFileBytes?: number;
  readonly writeTimeoutMs?: number;
  readonly onDiagnostic?: (
    code:
      | 'write_failed'
      | 'write_timeout'
      | 'queue_full'
      | 'active_limit'
      | 'logger_closed'
      | 'close_failed',
  ) => void;
}

/** Only explicit input/output is content-captured. Attributes also pass redaction. */
export interface SpanOptions {
  readonly parent?: SpanContext | null;
  readonly input?: unknown;
  readonly attributes?: Readonly<Record<string, unknown>>;
}

/** Opaque identifiers for joining spans across callback boundaries. */
export interface SpanContext {
  readonly runId: string;
  readonly spanId: string;
}

/** Only provider-supplied counters are retained; totals are never estimated. */
export interface ProviderUsage {
  readonly provider: 'gemini' | 'openai' | 'anthropic';
  readonly status: 'reported' | 'partial' | 'unavailable';
  readonly source: 'provider-reported';
  readonly inputTokens?: number;
  readonly outputTokens?: number;
  readonly totalTokens?: number;
  readonly cachedTokens?: number;
  readonly reasoningTokens?: number;
}
