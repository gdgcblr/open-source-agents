import type { AgentLoggerOptions, DeliveryStatus, LogEvent, LogSink } from './types.js';
import { SinkTimeout, withinTimeout } from './timeout.js';

/** Bounded serial delivery; diagnostics never contain input or sink error text. */
export class Delivery {
  private tail = Promise.resolve();
  private pending = 0;
  private written = 0;
  private failed = 0;
  private dropped = 0;
  private timedOut = false;

  constructor(
    private readonly sink: LogSink,
    private readonly capacity: number,
    private readonly timeoutMs: number,
    private readonly diagnostic: AgentLoggerOptions['onDiagnostic'],
  ) {}

  /** Args: sanitized event. Returns: nothing. Raises: none. */
  enqueue(event: LogEvent): void {
    if (this.pending >= this.capacity) {
      this.drop('queue_full');
      return;
    }
    this.pending++;
    this.tail = this.tail.then(async () => {
      try {
        if (this.timedOut) {
          this.failed++;
          return;
        }
        await withinTimeout(() => this.sink.write(event), this.timeoutMs);
        this.written++;
      } catch (error) {
        this.failed++;
        this.timedOut = error instanceof SinkTimeout;
        this.report(this.timedOut ? 'write_timeout' : 'write_failed');
      } finally {
        this.pending--;
      }
    });
  }

  /** Args: capture limit. Returns: nothing. Raises: none. */
  drop(code: 'active_limit' | 'queue_full' | 'logger_closed'): void {
    this.dropped++;
    this.report(code);
  }

  /** Args: none. Returns: delivery counters after queued writes. Raises: none. */
  async flush(): Promise<DeliveryStatus> {
    await this.tail;
    return this.status();
  }

  /** Args: none. Returns: final delivery counters. Raises: none. */
  async close(): Promise<DeliveryStatus> {
    await this.tail;
    try {
      await withinTimeout(() => this.sink.close?.(), this.timeoutMs);
    } catch {
      this.failed++;
      this.report('close_failed');
    }
    return this.status();
  }

  private status(): DeliveryStatus {
    return {
      success: this.failed === 0 && this.dropped === 0 && this.pending === 0,
      written: this.written,
      failed: this.failed,
      dropped: this.dropped,
      pending: this.pending,
    };
  }

  private report(
    code: Parameters<NonNullable<AgentLoggerOptions['onDiagnostic']>>[0],
  ): void {
    try {
      this.diagnostic?.(code);
    } catch {
      // Logging diagnostics cannot interrupt the application.
    }
  }
}
