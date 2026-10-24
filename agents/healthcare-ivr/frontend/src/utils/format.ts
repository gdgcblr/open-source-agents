const dateTimeFormat = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'short',
})

/** Playback position, e.g. `0:07`, `12:30` or `1:02:05`. */
export function formatTimestamp(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds))
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = String(seconds % 60).padStart(2, '0')
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, '0')}:${secs}` : `${minutes}:${secs}`
}

/** Call length, e.g. `45s`, `3m 41s` or `1h 2m`. */
export function formatDuration(totalSeconds: number | null): string {
  if (totalSeconds === null) return '—'
  const seconds = Math.round(totalSeconds)
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = seconds % 60
  if (hours > 0) return `${hours}h ${minutes}m`
  if (minutes > 0) return `${minutes}m ${secs}s`
  return `${secs}s`
}

export function formatDateTime(iso: string): string {
  return dateTimeFormat.format(new Date(iso))
}

/** Estimated cost in US dollars; amounts under a cent keep four decimals, e.g. `$0.0013`. */
export function formatUsd(amount: number | null): string {
  if (amount === null) return '—'
  return `$${amount.toFixed(amount !== 0 && Math.abs(amount) < 0.01 ? 4 : 2)}`
}

export function formatInr(amount: number | null): string {
  return amount === null ? '—' : `₹${amount.toLocaleString('en-IN')}`
}

/** A hospital-local `YYYY-MM-DD` date, e.g. `Mon, 26 Oct 2026`, without timezone shifts. */
export function formatLocalDate(isoDate: string): string {
  const [year, month, day] = isoDate.split('-').map(Number)
  return new Date(year, month - 1, day).toLocaleDateString('en-GB', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

/** A hospital-local `HH:MM[:SS]` time on a 12-hour clock, e.g. `9:15 AM`. */
export function formatClock(isoTime: string): string {
  const [hours, minutes] = isoTime.split(':').map(Number)
  const suffix = hours < 12 ? 'AM' : 'PM'
  return `${hours % 12 || 12}:${String(minutes).padStart(2, '0')} ${suffix}`
}
