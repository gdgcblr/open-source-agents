import { Link, useSearchParams } from 'react-router'

import { PAGE_SIZE, useCalls } from '../api/queries'
import { LiveCallsSection } from '../components/LiveCallsSection'
import { StatusBadge } from '../components/StatusBadge'
import { UploadButton } from '../components/UploadButton'
import { callTitle, sourceLabel } from '../utils/calls'
import { formatDateTime, formatDuration, formatUsd } from '../utils/format'
import { buttonStyles } from '../utils/ui'

export function CallsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const page = Math.max(1, Number(searchParams.get('page')) || 1)
  const { data, error, isPending, isPlaceholderData } = useCalls(page)

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1
  const goToPage = (next: number) => setSearchParams(next === 1 ? {} : { page: String(next) })

  return (
    <>
      <title>Call recordings – Hospital Reception IVR</title>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Call recordings</h1>
          <p className="mt-1 text-ink-muted">
            {data && data.total > 0
              ? `${data.total === 1 ? '1 call' : `${data.total} calls`} answered by the reception agent, ${formatUsd(data.total_cost_usd)} in AI costs`
              : 'Calls answered by the reception agent, with their recordings and transcripts'}
          </p>
        </div>
        <UploadButton />
      </div>

      <LiveCallsSection />

      <h2 className="mt-10 text-lg font-semibold">All calls</h2>

      {isPending && <p className="mt-6 text-ink-muted">Loading calls…</p>}

      {error && (
        <p role="alert" className="mt-6 rounded-lg border border-line bg-surface px-4 py-3">
          Couldn’t load calls. {error.message}
        </p>
      )}

      {data && data.total === 0 && (
        <div className="mt-6 rounded-xl border border-dashed border-line bg-surface px-6 py-12 text-center">
          <h2 className="text-lg font-semibold">No calls yet</h2>
          <p className="mx-auto mt-2 max-w-prose text-ink-muted">
            Calls to the hospital’s phone number appear here while they happen, and each
            transcript follows shortly after the call ends. To try transcription without a phone
            call, upload a recording.
          </p>
        </div>
      )}

      {data && data.items.length > 0 && (
        <div className="mt-3 overflow-x-auto rounded-xl border border-line bg-surface">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line text-ink-muted">
              <tr>
                <th scope="col" className="px-4 py-3 font-medium sm:px-5">Call</th>
                <th scope="col" className="hidden px-4 py-3 font-medium sm:table-cell">Received</th>
                <th scope="col" className="px-4 py-3 text-right font-medium">Length</th>
                <th scope="col" className="hidden px-4 py-3 text-right font-medium md:table-cell">
                  Speakers
                </th>
                <th scope="col" className="hidden px-4 py-3 text-right font-medium sm:table-cell">
                  AI cost
                </th>
                <th scope="col" className="px-4 py-3 font-medium sm:px-5">Transcript</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data.items.map((call) => (
                <tr key={call.id} className="relative hover:bg-surface-muted/60">
                  <td className="px-4 py-3 sm:px-5">
                    {/* The link's overlay makes the whole row clickable. */}
                    <Link
                      to={`/calls/${call.id}`}
                      className="font-semibold after:absolute after:inset-0"
                    >
                      {callTitle(call)}
                    </Link>
                    <p className="text-ink-muted">{sourceLabel(call)}</p>
                  </td>
                  <td className="hidden px-4 py-3 whitespace-nowrap sm:table-cell">
                    {formatDateTime(call.started_at)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums whitespace-nowrap">
                    {formatDuration(call.duration_seconds)}
                  </td>
                  <td className="hidden px-4 py-3 text-right tabular-nums md:table-cell">
                    {call.speaker_count ?? '—'}
                  </td>
                  <td className="hidden px-4 py-3 text-right tabular-nums sm:table-cell">
                    {formatUsd(call.total_cost_usd)}
                  </td>
                  <td className="px-4 py-3 sm:px-5">
                    <StatusBadge call={call} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {totalPages > 1 && (
        <nav aria-label="Pagination" className="mt-4 flex items-center justify-between gap-4 text-sm">
          <button
            type="button"
            className={buttonStyles.secondary}
            disabled={page <= 1}
            onClick={() => goToPage(page - 1)}
          >
            Previous
          </button>
          <span className="text-ink-muted">
            Page {page} of {totalPages}
          </span>
          <button
            type="button"
            className={buttonStyles.secondary}
            disabled={page >= totalPages || isPlaceholderData}
            onClick={() => goToPage(page + 1)}
          >
            Next
          </button>
        </nav>
      )}
    </>
  )
}
