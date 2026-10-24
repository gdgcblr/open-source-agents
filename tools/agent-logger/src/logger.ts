import { AsyncLocalStorage } from 'node:async_hooks';
import { randomUUID } from 'node:crypto';
import { Delivery } from './delivery.js';
import { FileSink } from './file-sink.js';
import { boundedInteger, validateName } from './privacy.js';
import { AgentSpan } from './span.js';
import { traceStream, type StreamSource, type StreamOptions } from './stream.js';
import { SPAN_KINDS } from './types.js';
import type {
  AgentLoggerOptions,
  DeliveryStatus,
  LogEvent,
  SpanContext,
  SpanKind,
  SpanOptions,
} from './types.js';

/** Logger-owned async context isolates concurrent runs and their child tools. */
export class AgentLogger {
  private readonly context = new AsyncLocalStorage<SpanContext>();
  private readonly active = new Set<AgentSpan>();
  private sequence = 0;
  private closing?: Promise<DeliveryStatus>;
  private closed = false;

  /** Args: internal delivery, capture setting and optional path. Returns: logger. Raises: none. */
  constructor(
    private readonly delivery: Delivery,
    private readonly captureContent: boolean,
    private readonly maxActiveSpans: number,
    readonly filePath?: string,
  ) {}

  /** Args: operation label, kind and options. Returns: manual span. Raises: on invalid configuration. */
  startSpan(name: string, kind: SpanKind, options: SpanOptions = {}): AgentSpan {
    validateSpanOptions(kind, options);
    const selected =
      options.parent === null ? undefined : (options.parent ?? this.context.getStore());
    const parent = selected === undefined ? undefined : Object.freeze({ ...selected });
    const context = Object.freeze({
      runId: parent?.runId ?? randomUUID(),
      spanId: randomUUID(),
    });
    const enabled = !this.closed && this.active.size < this.maxActiveSpans;
    if (!enabled) this.delivery.drop(this.closed ? 'logger_closed' : 'active_limit');
    const span: AgentSpan = new AgentSpan(
      {
        name: validateName(name),
        kind,
        context,
        ...(parent === undefined ? {} : { parent }),
        captureContent: this.captureContent,
        emit: (event): void => {
          if (enabled) this.emit(event);
        },
        onEnd: (): void => {
          this.active.delete(span);
        },
      },
      options,
    );
    if (enabled) this.active.add(span);
    return span;
  }

  /** Args: operation label, callback and optional input. Returns: unchanged result. Raises: original operation error. */
  async run<Result>(
    name: string,
    operation: () => Result | Promise<Result>,
    options: SpanOptions = {},
  ): Promise<Result> {
    return this.trace(name, 'run', operation, options);
  }

  /** Args: tool name and function. Returns: async wrapper preserving arguments and receiver. Raises: original tool error. */
  wrapTool<This, Arguments extends unknown[], Result>(
    name: string,
    operation: (this: This, ...args: Arguments) => Result | Promise<Result>,
  ): (this: This, ...args: Arguments) => Promise<Result> {
    return this.wrap(name, 'tool', operation);
  }

  /** Args: name, operation kind and function. Returns: typed async wrapper. Raises: original operation error. */
  wrap<This, Arguments extends unknown[], Result>(
    name: string,
    kind: SpanKind,
    operation: (this: This, ...args: Arguments) => Result | Promise<Result>,
  ): (this: This, ...args: Arguments) => Promise<Result> {
    validateName(name);
    validateSpanOptions(kind, {});
    const trace = this.trace.bind(this);
    return async function (this: This, ...args: Arguments): Promise<Result> {
      return trace(name, kind, () => operation.apply(this, args), {
        input: args,
      });
    };
  }

  /** Args: name, kind, async source and hooks. Returns: lazy pass-through stream. Raises: original source error. */
  stream<Chunk>(
    name: string,
    kind: SpanKind,
    source: StreamSource<Chunk>,
    options: StreamOptions<Chunk> = {},
  ): AsyncGenerator<Chunk, void, unknown> {
    validateName(name);
    validateSpanOptions(kind, options);
    const parent =
      options.parent === null
        ? null
        : (options.parent ?? this.context.getStore() ?? null);
    return traceStream(source, options, {
      start: (): AgentSpan => this.startSpan(name, kind, { ...options, parent }),
      within: <Result>(span: AgentSpan, operation: () => Result): Result =>
        this.context.run(span.context, operation),
    });
  }

  /** Args: name, kind, callback and options. Returns: unchanged result. Raises: original operation error. */
  async trace<Result>(
    name: string,
    kind: SpanKind,
    operation: (span: AgentSpan) => Result | Promise<Result>,
    options: SpanOptions = {},
  ): Promise<Result> {
    const span = this.startSpan(name, kind, options);
    return this.context.run(span.context, async () => {
      try {
        const result = await operation(span);
        span.end('completed', result);
        return result;
      } catch (error) {
        span.end('failed');
        throw error;
      }
    });
  }

  /** Args: none. Returns: delivery counters after queued events. Raises: none. */
  async flush(): Promise<DeliveryStatus> {
    return this.delivery.flush();
  }

  /** Args: none. Returns: final counters; abandoned spans become interrupted. Raises: none. */
  close(): Promise<DeliveryStatus> {
    if (this.closing !== undefined) return this.closing;
    for (const span of this.active) span.end('interrupted');
    this.closed = true;
    this.closing = this.delivery.close();
    return this.closing;
  }

  private emit(event: Omit<LogEvent, 'schemaVersion' | 'sequence' | 'timestamp'>): void {
    if (this.closed) return;
    this.delivery.enqueue({
      ...event,
      schemaVersion: 1,
      sequence: ++this.sequence,
      timestamp: new Date().toISOString(),
    });
  }
}

/** Args: optional local storage/capture settings. Returns: ready logger. Raises: on invalid options or unsafe storage. */
export async function createAgentLogger(
  options: AgentLoggerOptions = {},
): Promise<AgentLogger> {
  const capacity = boundedInteger(options.maxPendingEvents, 256, 1, 10000);
  const activeLimit = boundedInteger(options.maxActiveSpans, 1024, 1, 10000);
  const timeout = boundedInteger(options.writeTimeoutMs, 2000, 10, 30000);
  const maxBytes = boundedInteger(
    options.maxFileBytes,
    16 * 1024 * 1024,
    1024,
    1024 * 1024 * 1024,
  );
  if (options.captureContent !== undefined && typeof options.captureContent !== 'boolean')
    throw new TypeError('captureContent must be boolean.');
  if (options.sink && options.directory)
    throw new TypeError('Choose sink or directory, not both.');
  const sink =
    options.sink ?? (await FileSink.open(options.directory ?? '.agent-logs', maxBytes));
  if (typeof sink.write !== 'function')
    throw new TypeError('sink.write must be a function.');
  return new AgentLogger(
    new Delivery(sink, capacity, timeout, options.onDiagnostic),
    options.captureContent ?? false,
    activeLimit,
    sink instanceof FileSink ? sink.filePath : undefined,
  );
}

function validateSpanOptions(kind: SpanKind, options: SpanOptions): void {
  if (!(SPAN_KINDS as readonly string[]).includes(kind))
    throw new TypeError('Invalid span kind.');
  if (options.parent !== undefined && options.parent !== null) {
    for (const value of [options.parent.runId, options.parent.spanId]) {
      if (typeof value !== 'string' || !/^[a-f0-9-]{36}$/i.test(value))
        throw new TypeError('Invalid parent context.');
    }
  }
}
