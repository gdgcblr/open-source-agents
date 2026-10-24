import { useEffect, useRef } from 'react'

import type { CallEvent, SpeakerRole, TranscriptTurn } from '../api/types'
import type { LiveActivity } from '../hooks/useLiveCallStream'
import { eventTone, mergeTimeline, type EventTone } from '../utils/timeline'

const ROLE_LABEL: Record<SpeakerRole, string> = { agent: 'Receptionist', customer: 'Caller' }

const ACTIVITY_LABEL: Record<LiveActivity, string> = {
  caller_speaking: 'Caller is speaking…',
  agent_thinking: 'Receptionist is thinking…',
  agent_speaking: 'Receptionist is speaking…',
  listening: 'Listening…',
}

const TONE_CLASS: Record<EventTone, string> = {
  ok: 'bg-ok',
  danger: 'bg-danger',
  neutral: 'bg-ink-muted',
}

const timeOfDay = new Intl.DateTimeFormat(undefined, { timeStyle: 'medium' })

interface CallTimelineProps {
  turns: TranscriptTurn[]
  events: CallEvent[]
  /** Who is talking right now, while the call is live. */
  activity: LiveActivity | null
  live: boolean
}

/** The conversation and everything the system did, in one chronological list. */
export function CallTimeline({ turns, events, activity, live }: CallTimelineProps) {
  const items = mergeTimeline(turns, events)
  const scroller = useRef<HTMLDivElement>(null)
  const followLatest = useRef(true)

  // While live, keep the newest entry in view unless the reader has scrolled up.
  useEffect(() => {
    const element = scroller.current
    if (live && element && followLatest.current) element.scrollTop = element.scrollHeight
  }, [items.length, activity, live])

  return (
    <div
      ref={scroller}
      onScroll={(event) => {
        const element = event.currentTarget
        followLatest.current = element.scrollHeight - element.scrollTop - element.clientHeight < 48
      }}
      // Only a live call scrolls inside its own box (to follow new turns); a finished call
      // shows everything, so nothing important hides below an inner scrollbar.
      className={live ? 'max-h-[40rem] overflow-y-auto pr-1' : undefined}
    >
      {items.length === 0 && !live && <p className="text-ink-muted">Nothing was recorded for this call.</p>}
      <ol className="space-y-3">
        {items.map((item) =>
          item.kind === 'turn' ? (
            <li
              key={`turn-${item.at}-${item.turn.text.slice(0, 16)}`}
              className={item.turn.role === 'customer' ? 'pl-6' : 'pr-6'}
            >
              <p className="text-sm font-semibold text-ink-muted">{ROLE_LABEL[item.turn.role]}</p>
              <p
                className={`mt-1 rounded-lg px-3 py-2 leading-relaxed ${
                  item.turn.role === 'agent' ? 'bg-surface-muted' : 'border border-line bg-surface'
                }`}
              >
                {item.turn.text}
              </p>
            </li>
          ) : (
            <li
              key={`event-${item.at}-${item.event.type}`}
              className="flex items-start gap-2.5 py-0.5 text-sm text-ink-muted"
            >
              <span
                aria-hidden="true"
                className={`mt-1.5 size-1.5 shrink-0 rounded-full ${TONE_CLASS[eventTone(item.event.type)]}`}
              />
              <span className="min-w-0 flex-1">{item.event.message}</span>
              <time dateTime={item.event.created_at} className="shrink-0 tabular-nums">
                {timeOfDay.format(new Date(item.event.created_at))}
              </time>
            </li>
          ),
        )}
      </ol>
      {live && (
        <p role="status" className="mt-4 flex items-center gap-2 text-sm text-ink-muted">
          <span aria-hidden="true" className="size-2 rounded-full bg-danger motion-safe:animate-pulse" />
          {activity ? ACTIVITY_LABEL[activity] : 'Live'}
        </p>
      )}
    </div>
  )
}
