import {
  BaseLlm,
  type BaseLlmConnection,
  type LlmRequest,
  type LlmResponse,
} from '@google/adk';

/** Deterministic model for an actual ADK tool-calling run; no network or API key. */
export class OfflineModel extends BaseLlm {
  private calls = 0;

  /** Args: none. Returns: offline model. Raises: none. */
  constructor() {
    super({ model: 'offline-fixture' });
  }

  /** Args: ADK request. Returns: scripted provider-shaped responses. Raises: none. */
  override async *generateContentAsync(
    _request: LlmRequest,
  ): AsyncGenerator<LlmResponse, void> {
    this.calls++;
    if (this.calls === 1) {
      yield {
        content: {
          role: 'model',
          parts: [
            {
              functionCall: {
                id: 'weather-1',
                name: 'get_weather',
                args: { city: 'Bengaluru' },
              },
            },
          ],
        },
        usageMetadata: {
          promptTokenCount: 10,
          candidatesTokenCount: 4,
          totalTokenCount: 14,
        },
      };
      return;
    }
    yield {
      content: {
        role: 'model',
        parts: [
          { text: 'internal-thought-marker', thought: true },
          { text: 'Bengaluru: 25°C, clear.' },
        ],
      },
      usageMetadata: {
        promptTokenCount: 20,
        candidatesTokenCount: 6,
        totalTokenCount: 26,
      },
    };
  }

  /** Args: request. Returns: never. Raises: unsupported live-mode error. */
  override async connect(_request: LlmRequest): Promise<BaseLlmConnection> {
    throw new Error('Offline fixture does not support live mode.');
  }
}
