import type { CallSummary } from '../api/types'
import { formatDuration, formatUsd } from '../utils/format'

export function CostBreakdown({ call }: { call: CallSummary }) {
  const rows = [
    call.agent_cost_usd !== null && {
      label: `Voice agent (${formatDuration(call.agent_seconds)})`,
      amount: call.agent_cost_usd,
    },
    call.transcription_cost_usd !== null && {
      label: 'Recording transcription',
      amount: call.transcription_cost_usd,
    },
  ].filter((row) => row !== false)

  return (
    <section aria-labelledby="cost-heading" className="rounded-xl border border-line bg-surface p-4 sm:p-5">
      <h2 id="cost-heading" className="font-semibold">
        AI cost
      </h2>
      {rows.length === 0 ? (
        <p className="mt-2 text-sm text-ink-muted">Calculated once the call or transcription finishes.</p>
      ) : (
        <dl className="mt-3 space-y-1.5 text-sm">
          {rows.map((row) => (
            <div key={row.label} className="flex justify-between gap-4">
              <dt className="text-ink-muted">{row.label}</dt>
              <dd className="tabular-nums">{formatUsd(row.amount)}</dd>
            </div>
          ))}
          <div className="flex justify-between gap-4 border-t border-line pt-1.5 font-semibold">
            <dt>Total</dt>
            <dd className="tabular-nums">{formatUsd(call.total_cost_usd)}</dd>
          </div>
        </dl>
      )}
      <p className="mt-3 text-xs text-ink-muted">Estimated from Deepgram’s pay-as-you-go prices.</p>
    </section>
  )
}
