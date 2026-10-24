import type { CallSummary } from '../api/types'

type Tone = 'ok' | 'warn' | 'danger' | 'muted' | 'active'

const DOT_CLASS: Record<Tone, string> = {
  ok: 'bg-ok',
  warn: 'bg-warn',
  danger: 'bg-danger',
  muted: 'bg-ink-muted',
  active: 'bg-speaker-1 motion-safe:animate-pulse',
}

function describe(call: CallSummary): { label: string; tone: Tone } {
  switch (call.diarization_status) {
    case 'completed':
      return { label: 'Ready', tone: 'ok' }
    case 'processing':
      return { label: 'Transcribing', tone: 'active' }
    case 'failed':
      return { label: 'Failed', tone: 'danger' }
    case 'skipped':
      return { label: 'Not recorded', tone: 'muted' }
    case 'pending':
      if (call.source === 'upload') return { label: 'Queued', tone: 'warn' }
      if (call.status === 'in_progress') return { label: 'On the line', tone: 'active' }
      return { label: 'Waiting for recording', tone: 'warn' }
  }
}

export function StatusBadge({ call }: { call: CallSummary }) {
  const { label, tone } = describe(call)
  return (
    <span className="inline-flex items-center gap-2 whitespace-nowrap">
      <span aria-hidden="true" className={`size-2 rounded-full ${DOT_CLASS[tone]}`} />
      {label}
    </span>
  )
}
