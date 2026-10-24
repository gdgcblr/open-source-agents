const SPEAKER_PALETTE_SIZE = 5

/** Deepgram numbers speakers from 0; people count from 1. */
export function speakerLabel(speaker: number): string {
  return `Speaker ${speaker + 1}`
}

/** CSS colour for a speaker, consistent across the timeline, transcript and legend. */
export function speakerColor(speaker: number): string {
  return `var(--speaker-${(speaker % SPEAKER_PALETTE_SIZE) + 1})`
}
