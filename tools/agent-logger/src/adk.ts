import { BasePlugin } from '@google/adk';
import { InvocationSpans, finishSpan, visibleText } from './adk-state.js';
import type { AgentLogger } from './logger.js';
import type { DeliveryStatus } from './types.js';

type Hook<Name extends keyof BasePlugin> = BasePlugin[Name] extends (
  arg: infer Argument,
) => unknown
  ? Argument
  : never;

/** Observes ADK agent/model/tool hooks without replacing results or errors. */
export class AgentLoggerPlugin extends BasePlugin {
  private readonly runs = new Map<string, InvocationSpans>();

  /** Args: SDK logger. Returns: plugin for Runner.plugins. Raises: on invalid logger configuration. */
  constructor(private readonly logger: AgentLogger) {
    super('agent_logger');
  }

  /** Args: run context. Returns: undefined; ADK continues. Raises: none. */
  override async beforeRunCallback({
    invocationContext,
  }: Hook<'beforeRunCallback'>): Promise<undefined> {
    this.evictAbandonedRun();
    this.runs.get(invocationContext.invocationId)?.finish('interrupted');
    this.runs.set(
      invocationContext.invocationId,
      new InvocationSpans(this.logger, invocationContext),
    );
    return undefined;
  }

  /** Args: run context. Returns: completion. Raises: none. */
  override async afterRunCallback({
    invocationContext,
  }: Hook<'afterRunCallback'>): Promise<void> {
    const run = this.runs.get(invocationContext.invocationId);
    run?.finish(
      invocationContext.abortSignal?.aborted
        ? 'interrupted'
        : run.failed
          ? 'failed'
          : 'completed',
    );
    this.runs.delete(invocationContext.invocationId);
  }

  /** Args: agent and callback context. Returns: undefined. Raises: none. */
  override async beforeAgentCallback({
    callbackContext,
  }: Hook<'beforeAgentCallback'>): Promise<undefined> {
    const run = this.runs.get(callbackContext.invocationId);
    run?.ensureAgent(callbackContext);
    return undefined;
  }

  /** Args: agent callback context. Returns: undefined. Raises: none. */
  override async afterAgentCallback({
    callbackContext,
  }: Hook<'afterAgentCallback'>): Promise<undefined> {
    const run = this.runs.get(callbackContext.invocationId);
    if (run) {
      finishSpan(run.models, run.key(callbackContext), 'interrupted');
      finishSpan(run.agents, run.key(callbackContext), 'completed');
    }
    return undefined;
  }

  /** Args: model request and context. Returns: undefined. Raises: none. */
  override async beforeModelCallback({
    callbackContext,
    llmRequest,
  }: Hook<'beforeModelCallback'>): Promise<undefined> {
    const run = this.runs.get(callbackContext.invocationId);
    if (!run) return undefined;
    const key = run.key(callbackContext);
    finishSpan(run.models, key, 'interrupted');
    const parent = run.ensureAgent(callbackContext);
    run.models.set(
      key,
      this.logger.startSpan('adk.model', 'model', {
        parent: parent.context,
        attributes: { model: llmRequest.model ?? 'unreported' },
      }),
    );
    return undefined;
  }

  /** Args: model response and context. Returns: undefined. Raises: none. */
  override async afterModelCallback({
    callbackContext,
    llmResponse,
  }: Hook<'afterModelCallback'>): Promise<undefined> {
    const run = this.runs.get(callbackContext.invocationId);
    if (!run) return undefined;
    const span = run.models.get(run.key(callbackContext));
    if (llmResponse.errorCode) run.recordFailure(callbackContext, llmResponse);
    if (llmResponse.usageMetadata) span?.recordUsage('gemini', llmResponse);
    if (llmResponse.partial === true) return undefined;
    const status = llmResponse.interrupted
      ? 'interrupted'
      : llmResponse.errorCode
        ? 'failed'
        : 'completed';
    finishSpan(
      run.models,
      run.key(callbackContext),
      status,
      visibleText(llmResponse.content?.parts),
    );
    return undefined;
  }

  /** Args: model failure and context. Returns: undefined; original error propagates. Raises: none. */
  override async onModelErrorCallback({
    callbackContext,
    error,
  }: Hook<'onModelErrorCallback'>): Promise<undefined> {
    const run = this.runs.get(callbackContext.invocationId);
    if (run) {
      run.recordFailure(callbackContext, error);
      finishSpan(run.models, run.key(callbackContext), 'failed');
    }
    return undefined;
  }

  /** Args: tool, arguments and context. Returns: undefined. Raises: none. */
  override async beforeToolCallback({
    tool,
    toolArgs,
    toolContext,
  }: Hook<'beforeToolCallback'>): Promise<undefined> {
    const run = this.runs.get(toolContext.invocationId);
    if (!run) return undefined;
    const key = run.toolKey(toolContext);
    finishSpan(run.tools, key, 'interrupted');
    run.tools.set(
      key,
      this.logger.startSpan('adk.tool', 'tool', {
        parent: run.ensureAgent(toolContext).context,
        input: toolArgs,
        attributes: { tool: tool.name },
      }),
    );
    return undefined;
  }

  /** Args: tool response and context. Returns: undefined; result is preserved. Raises: none. */
  override async afterToolCallback({
    toolContext,
    result,
  }: Hook<'afterToolCallback'>): Promise<undefined> {
    const run = this.runs.get(toolContext.invocationId);
    if (run) finishSpan(run.tools, run.toolKey(toolContext), 'completed', result);
    return undefined;
  }

  /** Args: failed tool context. Returns: undefined; original error propagates. Raises: none. */
  override async onToolErrorCallback({
    toolContext,
  }: Hook<'onToolErrorCallback'>): Promise<undefined> {
    const run = this.runs.get(toolContext.invocationId);
    if (run) finishSpan(run.tools, run.toolKey(toolContext), 'failed');
    return undefined;
  }

  /** Args: none. Returns: delivery status; abandoned invocations become interrupted. Raises: none. */
  async close(): Promise<DeliveryStatus> {
    for (const run of this.runs.values())
      run.finish(run.failed ? 'failed' : 'interrupted');
    this.runs.clear();
    return this.logger.close();
  }

  private evictAbandonedRun(): void {
    if (this.runs.size < 128) return;
    const oldest = this.runs.entries().next().value;
    if (!oldest) return;
    oldest[1].root.setAttributes({ captureGap: 'invocation_limit' });
    oldest[1].finish('interrupted');
    this.runs.delete(oldest[0]);
  }
}
