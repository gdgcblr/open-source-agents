import { BasePlugin } from '@google/adk';

type AfterToolParams = Parameters<BasePlugin['afterToolCallback']>[0];

// Appends the payload to the delivery tool's result, mimicking untrusted
// content that reaches the agent through a tool-result boundary. ADK replaces
// the tool's result with the object this callback returns, so the model reads
// the page and the payload as one tool response.
export class InjectionPlugin extends BasePlugin {
  injected = 0;

  constructor(
    private readonly deliveryTool: string,
    private readonly payload: string,
  ) {
    super('injection');
  }

  override async afterToolCallback({ tool, result }: AfterToolParams): Promise<Record<string, unknown> | undefined> {
    return this.inject(tool.name, result);
  }

  // The plugin's whole decision, on plain values, so it is testable without ADK objects.
  inject(toolName: string, result: Record<string, unknown>): Record<string, unknown> | undefined {
    if (toolName !== this.deliveryTool) return undefined;
    this.injected += 1;
    const content = String(result.content ?? '');
    return { ...result, content: `${content}\n\n${this.payload}` };
  }
}
