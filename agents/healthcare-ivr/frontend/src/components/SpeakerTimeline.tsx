import type { MouseEvent } from 'react'

import type { Utterance } from '../api/types'
import { formatTimestamp } from '../utils/format'
import { speakerColor, speakerLabel } from '../utils/speakers'

interface SpeakerTimelineProps {
  utterances: Utterance[]
  duration: number
  currentTime: number
  onSeek: (seconds: number) => void
}

/** One lane per diarized speaker, segments drawn to scale, with a shared playhead. */
export function SpeakerTimeline({ utterances, duration, currentTime, onSeek }: SpeakerTimelineProps) {
  const speakers = [...new Set(utterances.map((u) => u.speaker))].sort((a, b) => a - b)
  if (duration <= 0 || speakers.length === 0) return null

  const toPercent = (seconds: number) => `${Math.min(100, Math.max(0, (seconds / duration) * 100))}%`

  function seekToPointer(event: MouseEvent<HTMLDivElement>) {
    const bounds = event.currentTarget.getBoundingClientRect()
    if (bounds.width === 0) return
    onSeek(((event.clientX - bounds.left) / bounds.width) * duration)
  }

  return (
    <figure>
      <figcaption className="sr-only">
        When each speaker talked. Use the transcript to jump to a specific line.
      </figcaption>
      <div className="flex gap-3">
        <ul className="flex flex-col gap-1.5 text-sm">
          {speakers.map((speaker) => (
            <li key={speaker} className="flex h-6 items-center gap-2 whitespace-nowrap">
              <span
                aria-hidden="true"
                className="size-2.5 rounded-full"
                style={{ background: speakerColor(speaker) }}
              />
              {speakerLabel(speaker)}
            </li>
          ))}
        </ul>

        <div className="min-w-0 flex-1">
          {/* Pointer shortcut only; the transcript list is the keyboard-accessible way to seek. */}
          <div
            aria-hidden="true"
            data-testid="speaker-tracks"
            className="relative cursor-pointer"
            onClick={seekToPointer}
          >
            <div className="flex flex-col gap-1.5">
              {speakers.map((speaker) => (
                <div
                  key={speaker}
                  data-testid={`speaker-lane-${speaker}`}
                  className="relative h-6 overflow-hidden rounded bg-surface-muted"
                >
                  {utterances
                    .filter((u) => u.speaker === speaker)
                    .map((u) => (
                      <span
                        key={u.start}
                        className="absolute inset-y-1 min-w-0.5 rounded-sm"
                        style={{
                          left: toPercent(u.start),
                          width: toPercent(u.end - u.start),
                          background: speakerColor(speaker),
                        }}
                      />
                    ))}
                </div>
              ))}
            </div>
            <span
              className="pointer-events-none absolute -inset-y-1 w-0.5 -translate-x-1/2 rounded-full bg-ink"
              style={{ left: toPercent(currentTime) }}
            />
          </div>
          <div className="mt-2 flex justify-between text-xs tabular-nums text-ink-muted">
            <span>0:00</span>
            <span>{formatTimestamp(duration)}</span>
          </div>
        </div>
      </div>
    </figure>
  )
}
