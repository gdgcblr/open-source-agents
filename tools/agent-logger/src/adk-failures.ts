/** Safe provider metadata. Messages are fixed strings, never provider payloads. */
export interface ProviderFailure {
  readonly errorCategory: keyof typeof MESSAGES;
  readonly errorMessage: string;
  readonly httpStatus?: number;
}

const MESSAGES = {
  authentication_failed: 'Google rejected the API key. Check GOOGLE_API_KEY in .env.',
  access_denied:
    'Google denied access. Check API key restrictions and project permissions.',
  model_unavailable:
    'The model is unavailable for this key or API. Check GEMINI_MODEL and model access.',
  quota_exceeded:
    'Google reported a quota or rate limit. Check AI Studio project quotas and billing before retrying.',
  provider_unavailable: 'The model provider is temporarily unavailable. Retry later.',
  network_failed: 'The model request could not reach Google. Check network connectivity.',
  content_blocked: 'The provider blocked the response. Try a different prompt.',
  provider_failed:
    'The model provider could not complete the request. Inspect project access and model configuration.',
} as const;

/** Args: provider error or ADK response. Returns: safe category, message and optional HTTP status. Raises: none. */
export function describeFailure(value: unknown): ProviderFailure {
  try {
    const details = failureDetails(value);
    const errorCategory = classify(details.status, details.text);
    return {
      errorCategory,
      errorMessage: MESSAGES[errorCategory],
      ...(details.status === undefined ? {} : { httpStatus: details.status }),
    };
  } catch {
    return { errorCategory: 'provider_failed', errorMessage: MESSAGES.provider_failed };
  }
}

function failureDetails(value: unknown): { status?: number; text: string } {
  if (!value || typeof value !== 'object') return { text: '' };
  const source = value as Record<string, unknown>;
  const message = source.message ?? source.errorMessage;
  if (typeof message === 'string') {
    try {
      const parsed: unknown = JSON.parse(message.slice(0, 16384));
      if (parsed && typeof parsed === 'object' && 'error' in parsed)
        return failureDetails(parsed.error);
    } catch {
      /* Most provider messages are plain text. */
    }
  }
  const rawStatus = source.code ?? source.status ?? source.errorCode;
  const numeric = typeof rawStatus === 'number' ? rawStatus : Number(rawStatus);
  return {
    ...(Number.isInteger(numeric) && numeric >= 400 && numeric <= 599
      ? { status: numeric }
      : {}),
    text: `${typeof rawStatus === 'string' ? rawStatus : ''} ${typeof message === 'string' ? message.slice(0, 16384) : ''}`,
  };
}

function classify(status: number | undefined, text: string): keyof typeof MESSAGES {
  if (status === 401 || /API_KEY_INVALID|UNAUTHENTICATED|API key not valid/i.test(text))
    return 'authentication_failed';
  if (status === 403 || /PERMISSION_DENIED/i.test(text)) return 'access_denied';
  if (status === 404 || /NOT_FOUND|model.*not.*found/i.test(text))
    return 'model_unavailable';
  if (status === 429 || /RESOURCE_EXHAUSTED|quota|rate.?limit/i.test(text))
    return 'quota_exceeded';
  if (status !== undefined && status >= 500) return 'provider_unavailable';
  if (/SAFETY|BLOCKLIST|PROHIBITED_CONTENT|RECITATION/i.test(text))
    return 'content_blocked';
  if (/fetch failed|ECONN|ENOTFOUND|network|timed?\s?out/i.test(text))
    return 'network_failed';
  return 'provider_failed';
}
