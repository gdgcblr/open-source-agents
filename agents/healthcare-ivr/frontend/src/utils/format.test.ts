import { describe, expect, it } from 'vitest'

import { formatClock, formatDuration, formatInr, formatLocalDate, formatTimestamp, formatUsd } from './format'

describe('formatTimestamp', () => {
  it.each([
    [0, '0:00'],
    [7.9, '0:07'],
    [750, '12:30'],
    [3725, '1:02:05'],
    [-3, '0:00'],
  ])('formats %s seconds as %s', (seconds, expected) => {
    expect(formatTimestamp(seconds)).toBe(expected)
  })
})

describe('formatDuration', () => {
  it.each([
    [null, '—'],
    [45.4, '45s'],
    [221, '3m 41s'],
    [3720, '1h 2m'],
  ])('formats %s seconds as %s', (seconds, expected) => {
    expect(formatDuration(seconds)).toBe(expected)
  })
})

describe('formatUsd', () => {
  it.each([
    [null, '—'],
    [0, '$0.00'],
    [0.0013, '$0.0013'],
    [0.2445, '$0.24'],
    [12.5, '$12.50'],
  ])('formats %s as %s', (amount, expected) => {
    expect(formatUsd(amount)).toBe(expected)
  })
})

describe('appointment formatting', () => {
  it('formats rupees with Indian digit grouping', () => {
    expect(formatInr(150000)).toBe('₹1,50,000')
    expect(formatInr(null)).toBe('—')
  })

  it('keeps hospital-local dates on the same day', () => {
    expect(formatLocalDate('2026-10-26')).toBe('Mon, 26 Oct 2026')
  })

  it.each([
    ['09:15:00', '9:15 AM'],
    ['00:30', '12:30 AM'],
    ['12:00:00', '12:00 PM'],
    ['17:45:00', '5:45 PM'],
  ])('formats %s as %s', (time, expected) => {
    expect(formatClock(time)).toBe(expected)
  })
})
