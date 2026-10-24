import { Link, useNavigate, useParams } from 'react-router'

import { ApiError, api } from '../api/client'
import { useCall, useDeleteCall } from '../api/queries'
import type { CallDetail } from '../api/types'
import { AppointmentCard } from '../components/AppointmentCard'
import { CostBreakdown } from '../components/CostBreakdown'
import { DiarizedTranscript } from '../components/DiarizedTranscript'
import { CallTimeline } from '../components/CallTimeline'
import { SpeakerTimeline } from '../components/SpeakerTimeline'
import { StatusBadge } from '../components/StatusBadge'
import { callTitle, languageLabel, sourceLabel } from '../utils/calls'
import { formatDateTime, formatDuration, formatUsd } from '../utils/format'
import { buttonStyles } from '../utils/ui'
import { useAudioClock } from '../hooks/useAudioClock'
import { useLiveCallStream } from '../hooks/useLiveCallStream'

function transcriptPlaceholder(call: CallDetail): string {
  switch (call.diarization_status) {
    case 'completed':
      return 'No speech was detected in the recording.'
    case 'failed':
      return 'No transcript is available for this call.'
    case 'skipped':
      return 'Call recording is turned off, so there is nothing to transcribe.'
    case 'processing':
      return 'Transcribing the recording…'
    case 'pending':
      if (call.source === 'upload') return 'Transcribing the recording…'
      return call.status === 'in_progress'
        ? 'The call is still in progress. The transcript appears shortly after it ends.'
        : 'Waiting for Twilio to deliver the recording.'
  }
}

function BackLink() {
  return (
    <Link to="/calls" className="inline-flex items-center gap-1 text-sm text-ink-muted hover:text-ink">
      <svg aria-hidden="true" viewBox="0 0 16 16" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.75">
        <path d="M10 3.5 5.5 8l4.5 4.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      All calls
    </Link>
  )
}

export function CallDetailPage() {
  const { callId = '' } = useParams()
  const navigate = useNavigate()
  const { data: call, error, isPending } = useCall(callId)
  const deleteCall = useDeleteCall()
  const { attachAudio, currentTime, duration: audioDuration, canSeek, seek } = useAudioClock()
  const isLive = call?.status === 'in_progress'
  const activity = useLiveCallStream(callId, isLive)

  if (isPending) {
    return <p className="text-ink-muted">Loading call…</p>
  }

  if (error) {
    const notFound = error instanceof ApiError && error.status === 404
    return (
      <>
        <BackLink />
        <p role="alert" className="mt-6 rounded-lg border border-line bg-surface px-4 py-3">
          {notFound ? 'This call doesn’t exist or has been deleted.' : `Couldn’t load the call. ${error.message}`}
        </p>
      </>
    )
  }

  const title = callTitle(call)
  const { utterances, turns } = call
  const isPhoneCall = call.source === 'phone'
  const activeIndex =
    currentTime > 0 ? utterances.findLastIndex((u) => u.start <= currentTime) : -1
  const timelineDuration =
    audioDuration || Math.max(call.duration_seconds ?? 0, utterances.at(-1)?.end ?? 0)

  const transcriptSection = (
    <section aria-labelledby="transcript-heading">
      <h2 id="transcript-heading" className="text-lg font-semibold">
        Transcript by speaker
      </h2>
      <p className="mt-1 text-sm text-ink-muted">
        Deepgram separated the voices in the recording. Select a line to play from there.
      </p>
      <div className="mt-4 overflow-hidden rounded-xl border border-line bg-surface">
        {utterances.length > 0 ? (
          <DiarizedTranscript
            utterances={utterances}
            activeIndex={activeIndex}
            canSeek={call.has_audio && canSeek}
            onSeek={seek}
          />
        ) : (
          <p className="px-5 py-8 text-ink-muted">{transcriptPlaceholder(call)}</p>
        )}
      </div>
    </section>
  )

  const timelineSection = (
    <section aria-labelledby="timeline-heading">
      <h2 id="timeline-heading" className="text-lg font-semibold">
        {isPhoneCall ? 'Conversation and events' : 'Events'}
      </h2>
      <p className="mt-1 text-sm text-ink-muted">
        {isLive
          ? 'Updates as the call happens.'
          : isPhoneCall
            ? 'What the receptionist heard, said and did during the call.'
            : 'What happened to this recording.'}
      </p>
      <div className="mt-4">
        <CallTimeline turns={turns} events={call.events} activity={activity} live={isLive} />
      </div>
    </section>
  )

  function handleDelete() {
    if (!window.confirm('Delete this call, its transcripts and its recording? This can’t be undone.')) {
      return
    }
    deleteCall.mutate(callId, { onSuccess: () => navigate('/calls') })
  }

  return (
    <>
      <title>{`${title} – Hospital Reception IVR`}</title>
      <BackLink />

      <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="flex flex-wrap items-center gap-3 text-2xl font-bold tracking-tight break-words sm:text-3xl">
            {title}
            {isLive && (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-danger/40 px-2.5 py-0.5 text-sm font-semibold text-danger">
                <span aria-hidden="true" className="size-2 rounded-full bg-danger motion-safe:animate-pulse" />
                Live
              </span>
            )}
          </h1>
          <dl className="mt-3 flex flex-wrap gap-x-8 gap-y-3 text-sm">
            <div>
              <dt className="text-ink-muted">Source</dt>
              <dd className="mt-0.5">{sourceLabel(call)}</dd>
            </div>
            {isPhoneCall && (
              <div>
                <dt className="text-ink-muted">Language</dt>
                <dd className="mt-0.5">{languageLabel(call.language)}</dd>
              </div>
            )}
            <div>
              <dt className="text-ink-muted">Received</dt>
              <dd className="mt-0.5">{formatDateTime(call.started_at)}</dd>
            </div>
            <div>
              <dt className="text-ink-muted">Length</dt>
              <dd className="mt-0.5 tabular-nums">{formatDuration(call.duration_seconds)}</dd>
            </div>
            <div>
              <dt className="text-ink-muted">Transcript</dt>
              <dd className="mt-0.5">
                <StatusBadge call={call} />
              </dd>
            </div>
            <div>
              <dt className="text-ink-muted">AI cost</dt>
              <dd className="mt-0.5 tabular-nums">{formatUsd(call.total_cost_usd)}</dd>
            </div>
          </dl>
        </div>
        <button
          type="button"
          className={buttonStyles.danger}
          disabled={deleteCall.isPending}
          onClick={handleDelete}
        >
          {deleteCall.isPending ? 'Deleting…' : 'Delete call'}
        </button>
      </div>

      {deleteCall.isError && (
        <p role="alert" className="mt-4 text-sm text-danger">
          Couldn’t delete the call. {deleteCall.error.message}
        </p>
      )}

      {call.diarization_status === 'failed' && (
        <div role="alert" className="mt-6 rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm">
          <strong className="font-semibold">Transcription failed.</strong> {call.diarization_error}
        </div>
      )}

      {/* What the call achieved and what it cost, ahead of the recording itself. */}
      <div className="mt-8 grid items-start gap-4 md:grid-cols-2">
        {call.appointments.map((appointment) => (
          <AppointmentCard key={appointment.id} appointment={appointment} />
        ))}
        <CostBreakdown call={call} />
      </div>

      {call.has_audio && (
        <section aria-labelledby="recording-heading" className="mt-8 rounded-xl border border-line bg-surface p-4 sm:p-6">
          <h2 id="recording-heading" className="text-lg font-semibold">
            Recording
          </h2>
          <audio ref={attachAudio} controls preload="metadata" src={api.audioUrl(call.id)} className="mt-4 w-full">
            Your browser can’t play this recording.
          </audio>
          {utterances.length > 0 && (
            <div className="mt-6">
              <SpeakerTimeline
                utterances={utterances}
                duration={timelineDuration}
                currentTime={currentTime}
                onSeek={seek}
              />
            </div>
          )}
        </section>
      )}

      {isLive ? (
        <div className="mt-8 space-y-8">
          {timelineSection}
          {transcriptSection}
        </div>
      ) : (
        <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
          {transcriptSection}
          {timelineSection}
        </div>
      )}
    </>
  )
}

