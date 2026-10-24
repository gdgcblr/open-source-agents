import { describe, expect, it } from 'vitest'

import type { CallSummary } from '../api/types'
import { languageLabel, sourceLabel } from './calls'

const call = (overrides: Partial<CallSummary>) => ({ source: 'phone', language: 'en', ...overrides }) as CallSummary

describe('call labels', () => {
  it.each([
    ['en', 'English'],
    ['hi', 'Hindi'],
    [null, 'Unknown'],
  ])('names language %s as %s', (code, expected) => {
    expect(languageLabel(code)).toBe(expected)
  })

  it('mentions the language only for calls not in English', () => {
    expect(sourceLabel(call({ language: 'en' }))).toBe('Phone call')
    expect(sourceLabel(call({ language: 'hi' }))).toBe('Phone call in Hindi')
    expect(sourceLabel(call({ source: 'upload', language: null }))).toBe('Uploaded recording')
  })
})
