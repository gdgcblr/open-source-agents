import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Utterance } from '../api/types'
import { SpeakerTimeline } from './SpeakerTimeline'

const utterances: Utterance[] = [
  { speaker: 0, start: 0, end: 10, text: 'Thanks for calling.', confidence: 0.97 },
  { speaker: 1, start: 10, end: 25, text: 'My order is late.', confidence: 0.94 },
  { speaker: 0, start: 25, end: 30, text: 'Let me check.', confidence: 0.96 },
]

describe('SpeakerTimeline', () => {
  it('draws one lane per speaker with segments scaled to the call length', () => {
    render(<SpeakerTimeline utterances={utterances} duration={40} currentTime={0} onSeek={vi.fn()} />)

    expect(screen.getByText('Speaker 1')).toBeInTheDocument()
    expect(screen.getByText('Speaker 2')).toBeInTheDocument()
    const customerSegments = screen.getByTestId('speaker-lane-1').querySelectorAll('span')
    expect(customerSegments).toHaveLength(1)
    expect(customerSegments[0]).toHaveStyle({ left: '25%', width: '37.5%' })
    expect(screen.getByTestId('speaker-lane-0').querySelectorAll('span')).toHaveLength(2)
  })

  it('seeks to the clicked point in the call', () => {
    const onSeek = vi.fn()
    render(<SpeakerTimeline utterances={utterances} duration={40} currentTime={0} onSeek={onSeek} />)
    const tracks = screen.getByTestId('speaker-tracks')
    vi.spyOn(tracks, 'getBoundingClientRect').mockReturnValue(new DOMRect(100, 0, 400, 60))

    fireEvent.click(tracks, { clientX: 300 })

    expect(onSeek).toHaveBeenCalledWith(20)
  })

  it('renders nothing before the duration is known', () => {
    const { container } = render(
      <SpeakerTimeline utterances={utterances} duration={0} currentTime={0} onSeek={vi.fn()} />,
    )

    expect(container).toBeEmptyDOMElement()
  })
})
