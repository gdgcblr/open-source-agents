import type { ProviderUsage } from './types.js';

type Counter =
  'inputTokens' | 'outputTokens' | 'totalTokens' | 'cachedTokens' | 'reasoningTokens';

/** Args: provider and completed response. Returns: normalized counters. Raises: TypeError for unsupported provider. */
export function normalizeUsage(
  provider: ProviderUsage['provider'],
  response: unknown,
): ProviderUsage {
  if (!['gemini', 'openai', 'anthropic'].includes(provider))
    throw new TypeError('Unsupported usage provider.');
  const empty: ProviderUsage = {
    provider,
    source: 'provider-reported',
    status: 'unavailable',
  };
  try {
    const usage = property(response, provider === 'gemini' ? 'usageMetadata' : 'usage');
    const fields = usageFields(provider, usage);
    const counters: Partial<Record<Counter, number>> = {};
    for (const [name, value] of Object.entries(fields)) {
      if (typeof value === 'number' && Number.isSafeInteger(value) && value >= 0)
        counters[name as Counter] = value;
    }
    if (Object.keys(counters).length === 0) return empty;
    const status =
      counters.inputTokens !== undefined && counters.outputTokens !== undefined
        ? 'reported'
        : 'partial';
    return { ...empty, ...counters, status };
  } catch {
    return empty;
  }
}

function usageFields(
  provider: ProviderUsage['provider'],
  usage: unknown,
): Record<Counter, unknown> {
  if (provider === 'gemini')
    return {
      inputTokens: property(usage, 'promptTokenCount'),
      outputTokens: property(usage, 'candidatesTokenCount'),
      totalTokens: property(usage, 'totalTokenCount'),
      cachedTokens: property(usage, 'cachedContentTokenCount'),
      reasoningTokens: property(usage, 'thoughtsTokenCount'),
    };
  const inputDetails =
    property(usage, 'input_tokens_details') ?? property(usage, 'prompt_tokens_details');
  const outputDetails =
    property(usage, 'output_tokens_details') ??
    property(usage, 'completion_tokens_details');
  return {
    inputTokens: property(usage, 'input_tokens') ?? property(usage, 'prompt_tokens'),
    outputTokens:
      property(usage, 'output_tokens') ?? property(usage, 'completion_tokens'),
    totalTokens: property(usage, 'total_tokens'),
    cachedTokens:
      provider === 'anthropic'
        ? property(usage, 'cache_read_input_tokens')
        : property(inputDetails, 'cached_tokens'),
    reasoningTokens: property(outputDetails, 'reasoning_tokens'),
  };
}

function property(value: unknown, key: string): unknown {
  if (value === null || typeof value !== 'object') return undefined;
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && 'value' in descriptor ? descriptor.value : undefined;
}
