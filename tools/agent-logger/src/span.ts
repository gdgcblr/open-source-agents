import { performance } from 'node:perf_hooks';
import { sanitize } from './privacy.js';
import { normalizeUsage } from './usage.js';
import type {
  JsonValue,
  LogEvent,
  SpanContext,
  SpanKind,
  SpanOptions,
  SpanStatus,
  ProviderUsage,
} from './types.js';

interface SpanConfiguration {
  readonly context: SpanContext;
  readonly parent?: SpanContext;
  readonly name: string;
  readonly kind: SpanKind;
  readonly captureContent: boolean;
  readonly emit: (
    event: Omit<LogEvent, 'schemaVersion' | 'sequence' | 'timestamp'>,
  ) => void;
  readonly onEnd: () => void;
}

/** One timed operation. Ending a span twice is harmless. */
export class AgentSpan {
  readonly context: SpanContext;
  private readonly startedAt = performance.now();
  private readonly metadata: Record<string, JsonValue> = {};
  private ended = false;
  private usage: ProviderUsage | undefined;
  private capturedOutput: JsonValue | undefined;

  /** Args: internal configuration and span options. Returns: span. Raises: none. */
  constructor(
    private readonly config: SpanConfiguration,
    options: SpanOptions,
  ) {
    this.context = config.context;
    if (options.attributes) this.setAttributes(options.attributes);
    this.config.emit({
      ...this.base(),
      phase: 'started',
      data: sanitize({
        attributes: this.metadata,
        ...(config.captureContent && options.input !== undefined
          ? { input: options.input }
          : {}),
      }),
    });
  }

  /** Args: explicitly selected metadata. Returns: nothing. Raises: none. */
  setAttributes(attributes: Readonly<Record<string, unknown>>): void {
    if (this.ended) return;
    const value = sanitize(attributes);
    if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
      for (const [key, entry] of Object.entries(value)) {
        if (Object.hasOwn(this.metadata, key) || Object.keys(this.metadata).length < 32) {
          this.metadata[key] = entry;
        }
      }
    }
  }

  /** Args: provider and completed response. Returns: normalized counters. Raises: TypeError for unsupported provider. */
  recordUsage(provider: ProviderUsage['provider'], response: unknown): ProviderUsage {
    const usage = normalizeUsage(provider, response);
    if (!this.ended) this.usage = usage;
    return usage;
  }

  /** Args: explicitly selected visible output. Returns: nothing. Raises: none. */
  captureOutput(value: unknown): void {
    if (!this.ended && this.config.captureContent) this.capturedOutput = sanitize(value);
  }

  /** Args: terminal status and optional output. Returns: nothing. Raises: TypeError for invalid status. */
  end(status: SpanStatus = 'completed', output?: unknown): void {
    if (this.ended) return;
    if (!['completed', 'failed', 'interrupted'].includes(status))
      throw new TypeError('Invalid span status.');
    this.ended = true;
    const result = output === undefined ? this.capturedOutput : output;
    this.config.emit({
      ...this.base(),
      phase: 'finished',
      status,
      durationMs: Math.round((performance.now() - this.startedAt) * 100) / 100,
      data: sanitize({
        attributes: this.metadata,
        ...(this.usage === undefined ? {} : { usage: this.usage }),
        ...(this.config.captureContent && result !== undefined ? { output: result } : {}),
      }),
    });
    this.config.onEnd();
  }

  private base(): Pick<LogEvent, 'runId' | 'spanId' | 'parentSpanId' | 'kind' | 'name'> {
    return {
      ...this.context,
      kind: this.config.kind,
      name: this.config.name,
      ...(this.config.parent === undefined
        ? {}
        : { parentSpanId: this.config.parent.spanId }),
    };
  }
}
