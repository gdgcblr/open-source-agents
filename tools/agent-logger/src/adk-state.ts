import type { BaseAgent, Context, InvocationContext } from '@google/adk';
import type { AgentLogger } from './logger.js';
import type { AgentSpan } from './span.js';
import type { SpanStatus } from './types.js';
import { describeFailure } from './adk-failures.js';

/** Per-invocation state; branches and function-call IDs prevent cross-run pairing. */
export class InvocationSpans {
  failed = false;
  readonly agents = new Map<string, AgentSpan>();
  readonly models = new Map<string, AgentSpan>();
  readonly tools = new Map<string, AgentSpan>();
  readonly root: AgentSpan;
  private readonly toolIds = new WeakMap<Context, string>();
  private nextToolId = 0;

  constructor(
    readonly logger: AgentLogger,
    invocation: InvocationContext,
  ) {
    this.root = logger.startSpan('adk.run', 'run', {
      parent: null,
      input: visibleText(invocation.userContent?.parts),
      attributes: { framework: 'google-adk' },
    });
  }

  /** Args: callback context. Returns: branch/agent identity key. Raises: none. */
  key(context: Context): string {
    return JSON.stringify([
      context.invocationContext.branch ?? '',
      context.invocationContext.agent?.name ?? 'agent',
    ]);
  }

  /** Args: callback context. Returns: parent scope for this observed agent. Raises: none. */
  ensureAgent(context: Context): AgentSpan {
    const invocation = context.invocationContext;
    return invocation.agent
      ? this.agentScope(invocation.agent, invocation.branch ?? '')
      : this.root;
  }

  /** Args: model callback context and failure. Returns: nothing. Raises: none. */
  recordFailure(context: Context, failure: unknown): void {
    this.failed = true;
    const attributes = { ...describeFailure(failure) };
    this.root.setAttributes(attributes);
    this.models.get(this.key(context))?.setAttributes(attributes);
  }

  private agentScope(agent: BaseAgent, branch: string): AgentSpan {
    const key = JSON.stringify([branch, agent.name]);
    const existing = this.agents.get(key);
    if (existing) return existing;
    const parent = agent.parentAgent
      ? this.agentScope(agent.parentAgent, branch)
      : this.root;
    const span = this.logger.startSpan('adk.agent.scope', 'agent', {
      parent: parent.context,
      attributes: { agent: agent.name, interval: 'observed-callbacks' },
    });
    this.agents.set(key, span);
    return span;
  }

  /** Args: tool context. Returns: stable tool correlation within invocation. Raises: none. */
  toolKey(context: Context): string {
    const key =
      context.functionCallId ??
      this.toolIds.get(context) ??
      `generated-${++this.nextToolId}`;
    this.toolIds.set(context, key);
    return JSON.stringify([this.key(context), key]);
  }

  /** Args: terminal status. Returns: nothing. Raises: none. */
  finish(status: SpanStatus): void {
    for (const spans of [this.tools, this.models]) {
      for (const span of spans.values()) span.end('interrupted');
      spans.clear();
    }
    for (const span of this.agents.values())
      span.end(status === 'completed' ? 'completed' : 'interrupted');
    this.agents.clear();
    this.root.end(status);
  }
}

/** Args: ADK content parts. Returns: visible text only. Raises: none. */
export function visibleText(
  parts: readonly { text?: string; thought?: boolean }[] | undefined,
): string | undefined {
  const text = parts
    ?.filter((part) => part.thought !== true && typeof part.text === 'string')
    .slice(0, 32)
    .map((part) => part.text?.slice(0, 1024))
    .join('\n');
  return text || undefined;
}

/** Args: span map, key, status and output. Returns: nothing. Raises: none. */
export function finishSpan(
  spans: Map<string, AgentSpan>,
  key: string,
  status: SpanStatus,
  output?: unknown,
): void {
  spans.get(key)?.end(status, output);
  spans.delete(key);
}
