import type { AgentSpan } from './span.js';
import type { SpanOptions } from './types.js';

/** A stream or lazy factory; no source iteration occurs before the consumer asks. */
export type StreamSource<Chunk> =
  | AsyncIterable<Chunk>
  | ((span: AgentSpan) => AsyncIterable<Chunk> | Promise<AsyncIterable<Chunk>>);
export interface StreamOptions<Chunk> extends SpanOptions {
  readonly onChunk?: (chunk: Chunk, span: AgentSpan) => void | Promise<void>;
}

interface StreamRuntime {
  start(): AgentSpan;
  within<Result>(span: AgentSpan, operation: () => Result): Result;
}

/** Args: source, hooks, context runtime. Returns: pass-through iterator. Raises: original source error. */
export async function* traceStream<Chunk>(
  source: StreamSource<Chunk>,
  options: StreamOptions<Chunk>,
  runtime: StreamRuntime,
): AsyncGenerator<Chunk, void, unknown> {
  const span = runtime.start();
  let finished = false;
  let failed = false;
  let iterator: AsyncIterator<Chunk> | undefined;
  try {
    const iterable =
      typeof source === 'function'
        ? await runtime.within(span, () => source(span))
        : source;
    iterator = runtime.within(span, () => iterable[Symbol.asyncIterator]());
    while (true) {
      const result = await runtime.within(span, () => iterator!.next());
      if (result.done) {
        finished = true;
        break;
      }
      await notifyChunk(options, result.value, span, runtime);
      yield result.value;
    }
  } catch (error) {
    failed = true;
    span.end('failed');
    throw error;
  } finally {
    try {
      if (!finished) await closeIterator(iterator, span, runtime, failed);
    } finally {
      span.end(finished ? 'completed' : 'interrupted');
    }
  }
}

async function closeIterator<Chunk>(
  iterator: AsyncIterator<Chunk> | undefined,
  span: AgentSpan,
  runtime: StreamRuntime,
  sourceFailed: boolean,
): Promise<void> {
  try {
    if (iterator?.return) await runtime.within(span, () => iterator.return!());
  } catch (error) {
    if (!sourceFailed) {
      span.end('failed');
      throw error;
    }
  }
}

async function notifyChunk<Chunk>(
  options: StreamOptions<Chunk>,
  chunk: Chunk,
  span: AgentSpan,
  runtime: StreamRuntime,
): Promise<void> {
  try {
    await runtime.within(span, () => options.onChunk?.(chunk, span));
  } catch {
    span.setAttributes({ captureGap: 'chunk_hook_failed' });
  }
}
