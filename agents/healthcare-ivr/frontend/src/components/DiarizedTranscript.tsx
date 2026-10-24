import type { Utterance } from '../api/types'
import { formatTimestamp } from '../utils/format'
import { speakerColor, speakerLabel } from '../utils/speakers'

interface DiarizedTranscriptProps {
  utterances: Utterance[]
  activeIndex: number
  canSeek: boolean
  onSeek: (seconds: number) => void
}

export function DiarizedTranscript({ utterances, activeIndex, canSeek, onSeek }: DiarizedTranscriptProps) {
  return (
    <ol className="divide-y divide-line">
      {utterances.map((utterance, index) => {
        const isActive = index === activeIndex
        return (
          <li key={`${utterance.start}-${index}`}>
            <button
              type="button"
              disabled={!canSeek}
              aria-current={isActive ? 'true' : undefined}
              onClick={() => onSeek(utterance.start)}
              className={`grid w-full grid-cols-[3.25rem_minmax(0,1fr)] gap-x-4 px-4 py-3 text-left disabled:cursor-default sm:px-5 ${
                isActive ? 'bg-surface-muted' : 'enabled:hover:bg-surface-muted/60'
              }`}
              style={isActive ? { boxShadow: `inset 3px 0 0 ${speakerColor(utterance.speaker)}` } : undefined}
            >
              <span className="pt-px text-sm tabular-nums text-ink-muted">
                {canSeek && <span className="sr-only">Play from </span>}
                {formatTimestamp(utterance.start)}
              </span>
              <span>
                <span className="flex items-center gap-2 text-sm font-semibold">
                  <span
                    aria-hidden="true"
                    className="size-2 rounded-full"
                    style={{ background: speakerColor(utterance.speaker) }}
                  />
                  {speakerLabel(utterance.speaker)}
                </span>
                <span className="mt-1 block max-w-prose leading-relaxed">{utterance.text}</span>
              </span>
            </button>
          </li>
        )
      })}
    </ol>
  )
}
