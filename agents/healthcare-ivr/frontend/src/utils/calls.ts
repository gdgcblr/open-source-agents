import type { CallSummary } from '../api/types'

export function callTitle(call: CallSummary): string {
  return call.caller_number ?? call.title ?? (call.source === 'phone' ? 'Unknown caller' : 'Recording')
}

const LANGUAGE_NAMES: Record<string, string> = { en: 'English', hi: 'Hindi' }

export function languageLabel(code: string | null): string {
  if (!code) return 'Unknown'
  return LANGUAGE_NAMES[code] ?? code
}

/** "Phone call", "Phone call in Hindi" or "Uploaded recording". */
export function sourceLabel(call: CallSummary): string {
  if (call.source === 'upload') return 'Uploaded recording'
  return call.language && call.language !== 'en'
    ? `Phone call in ${languageLabel(call.language)}`
    : 'Phone call'
}
