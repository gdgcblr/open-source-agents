import { Link } from 'react-router'

import { useLiveCalls } from '../api/queries'
import type { SpeakerRole } from '../api/types'
import { useNow } from '../hooks/useNow'
import { callTitle, languageLabel } from '../utils/calls'
import { formatTimestamp } from '../utils/format'

const ROLE_LABEL: Record<SpeakerRole, string> = { agent: 'Receptionist', customer: 'Caller' }

export function LiveCallsSection() {
  const { data } = useLiveCalls()
  const now = useNow()
  const calls = data?.items ?? []

  return (
    <section aria-labelledby="live-heading" className="mt-6">
      <h2 id="live-heading" className="flex items-center gap-2 text-lg font-semibold">
        <span
          aria-hidden="true"
          className={`size-2.5 rounded-full ${
            calls.length > 0 ? 'bg-danger motion-safe:animate-pulse' : 'bg-ink-muted/50'
          }`}
        />
        Live now
        {calls.length > 0 && <span className="font-normal text-ink-muted">({calls.length})</span>}
      </h2>

      {calls.length === 0 ? (
        <p className="mt-1 text-sm text-ink-muted">
          No calls in progress. Calls appear here as soon as the receptionist answers.
        </p>
      ) : (
        <ul className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {calls.map((call) => (
            <li key={call.id}>
              <Link
                to={`/calls/${call.id}`}
                className="block h-full rounded-xl border border-line bg-surface p-4 transition-colors hover:border-ink-muted"
              >
                <div className="flex items-baseline justify-between gap-3">
                  <p className="font-semibold">
                    {callTitle(call)}
                    {call.language && call.language !== 'en' && (
                      <span className="ml-2 text-sm font-normal text-ink-muted">
                        {languageLabel(call.language)}
                      </span>
                    )}
                  </p>
                  <p className="text-sm text-ink-muted tabular-nums">
                    <span className="sr-only">On the line for </span>
                    {formatTimestamp((now - Date.parse(call.started_at)) / 1000)}
                  </p>
                </div>
                <p className="mt-2 line-clamp-2 text-sm text-ink-muted">
                  {call.latest_turn ? (
                    <>
                      <span className="font-semibold text-ink">
                        {ROLE_LABEL[call.latest_turn.role]}:
                      </span>{' '}
                      {call.latest_turn.text}
                    </>
                  ) : (
                    'Connecting…'
                  )}
                </p>
                <p className="mt-3 text-sm font-semibold">Follow live</p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
