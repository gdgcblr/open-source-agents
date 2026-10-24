import { useState } from 'react'

import { useAnalytics } from '../api/queries'
import type { AnalyticsSummary } from '../api/types'
import { languageLabel } from '../utils/calls'
import { formatInr, formatUsd } from '../utils/format'

const PERIODS = [
  { days: 7, label: '7 days' },
  { days: 30, label: '30 days' },
  { days: 90, label: '90 days' },
  { days: 0, label: 'All time' },
]

function percent(rate: number | null): string {
  return rate === null ? '—' : `${Math.round(rate * 100)}%`
}

/** Calls → bookings → attended visits, as thin bars on one scale with the rate between stages. */
function ConversionFunnel({ summary }: { summary: AnalyticsSummary }) {
  const stages = [
    { label: 'Calls handled', value: summary.phone_calls },
    {
      label: 'Appointments booked',
      value: summary.appointments_booked,
      rate: `${percent(summary.booking_rate)} of calls`,
    },
    {
      label: 'Appointments attended',
      value: summary.appointments_completed,
      rate: `${percent(summary.completion_rate)} of visits with a recorded outcome`,
    },
  ]
  const largest = Math.max(...stages.map((stage) => stage.value), 1)

  return (
    <ol className="space-y-4">
      {stages.map((stage) => (
        <li key={stage.label}>
          <div className="flex items-baseline justify-between gap-4">
            <p className="font-semibold">{stage.label}</p>
            <p className="text-lg font-semibold">{stage.value.toLocaleString()}</p>
          </div>
          <div aria-hidden="true" className="mt-1.5 h-2 rounded-full bg-surface-muted">
            <div
              className="h-2 rounded-full bg-ink/70"
              style={{ width: `${(stage.value / largest) * 100}%` }}
            />
          </div>
          {stage.rate && <p className="mt-1 text-sm text-ink-muted">{stage.rate}</p>}
        </li>
      ))}
    </ol>
  )
}

function StatTile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-lg border border-line px-4 py-3">
      <dt className="text-sm text-ink-muted">{label}</dt>
      <dd className="mt-1 text-xl font-semibold">{value}</dd>
      {note && <dd className="mt-0.5 text-xs text-ink-muted">{note}</dd>}
    </div>
  )
}

export function PerformanceSection() {
  const [days, setDays] = useState(30)
  const { data, error, isPending } = useAnalytics(days)

  return (
    <section
      aria-labelledby="performance"
      className="rounded-xl border border-line bg-surface px-5 py-6 sm:px-8 sm:py-8"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="performance" className="scroll-mt-6 text-xl font-bold">
          Performance
        </h2>
        <div role="group" aria-label="Period" className="flex gap-1">
          {PERIODS.map((period) => (
            <button
              key={period.days}
              type="button"
              aria-pressed={period.days === days}
              onClick={() => setDays(period.days)}
              className={`rounded-md px-2.5 py-1 text-sm font-semibold ${
                period.days === days ? 'bg-surface-muted text-ink' : 'text-ink-muted hover:text-ink'
              }`}
            >
              {period.label}
            </button>
          ))}
        </div>
      </div>
      <p className="mt-1 text-sm text-ink-muted">
        A booking only earns revenue once the patient attends, so mark visits as attended on the
        Appointments page.
      </p>

      {isPending && <p className="mt-6 text-ink-muted">Loading performance…</p>}
      {error && (
        <p role="alert" className="mt-6 text-danger">
          Couldn’t load performance. {error.message}
        </p>
      )}

      {data && (
        <div className="mt-6 grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div>
            <h3 className="sr-only">Conversions</h3>
            <ConversionFunnel summary={data} />
            <dl className="mt-4 flex flex-wrap gap-x-6 gap-y-1 text-sm text-ink-muted">
              <div className="flex gap-1.5">
                <dt>Awaiting outcome</dt>
                <dd className="font-semibold text-ink">{data.appointments_pending}</dd>
              </div>
              <div className="flex gap-1.5">
                <dt>No-shows</dt>
                <dd className="font-semibold text-ink">{data.appointments_no_show}</dd>
              </div>
              <div className="flex gap-1.5">
                <dt>Cancelled</dt>
                <dd className="font-semibold text-ink">{data.appointments_cancelled}</dd>
              </div>
            </dl>
            {Object.keys(data.calls_by_language).length > 0 && (
              <dl className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-sm text-ink-muted">
                {Object.entries(data.calls_by_language).map(([language, count]) => (
                  <div key={language} className="flex gap-1.5">
                    <dt>Calls in {languageLabel(language === 'unknown' ? null : language)}</dt>
                    <dd className="font-semibold text-ink">{count}</dd>
                  </div>
                ))}
              </dl>
            )}
          </div>

          <div>
            <h3 className="sr-only">Spend and revenue</h3>
            <dl className="grid grid-cols-2 gap-3">
              <StatTile
                label="AI spend"
                value={formatUsd(data.ai_cost_usd)}
                note={`${data.voice_agent_minutes.toLocaleString()} voice-agent minutes`}
              />
              <StatTile
                label="Revenue from attended visits"
                value={formatInr(data.revenue_inr)}
                note="Consultation fees"
              />
              <StatTile label="AI cost per booking" value={formatUsd(data.cost_per_booking_usd)} />
              <StatTile
                label="AI cost per attended visit"
                value={formatUsd(data.cost_per_completed_usd)}
              />
            </dl>
            <p className="mt-3 text-xs text-ink-muted">
              Costs are estimated from Deepgram’s per-minute prices; Deepgram doesn’t report token
              counts for the LLMs it runs.
            </p>
          </div>
        </div>
      )}
    </section>
  )
}
