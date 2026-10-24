import type { CallEvent, CallEventType, TranscriptTurn } from '../api/types'

export type TimelineItem =
  | { kind: 'turn'; at: number; turn: TranscriptTurn }
  | { kind: 'event'; at: number; event: CallEvent }

/** Turns and events in the order they happened; ties keep events before the turn they caused. */
export function mergeTimeline(turns: TranscriptTurn[], events: CallEvent[]): TimelineItem[] {
  const items: TimelineItem[] = [
    ...events.map((event) => ({ kind: 'event' as const, at: Date.parse(event.created_at), event })),
    ...turns.map((turn) => ({ kind: 'turn' as const, at: Date.parse(turn.created_at), turn })),
  ]
  // Array.prototype.sort is stable, so equal timestamps keep the order above.
  return items.sort((a, b) => a.at - b.at)
}

export type EventTone = 'ok' | 'danger' | 'neutral'

const EVENT_TONE: Partial<Record<CallEventType, EventTone>> = {
  appointment_booked: 'ok',
  appointment_completed: 'ok',
  transcription_completed: 'ok',
  recording_failed: 'danger',
  tool_error: 'danger',
  agent_error: 'danger',
  transcription_failed: 'danger',
}

export function eventTone(type: CallEventType): EventTone {
  return EVENT_TONE[type] ?? 'neutral'
}
