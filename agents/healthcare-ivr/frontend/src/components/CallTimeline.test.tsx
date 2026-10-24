import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { CallEvent, TranscriptTurn } from '../api/types'
import { mergeTimeline } from '../utils/timeline'
import { CallTimeline } from './CallTimeline'

const TURNS: TranscriptTurn[] = [
  { role: 'agent', text: 'Thank you for calling.', created_at: '2026-10-24T07:00:01Z' },
  { role: 'customer', text: 'Book me with Dr. Deshmukh.', created_at: '2026-10-24T07:00:05Z' },
]
const EVENTS: CallEvent[] = [
  { type: 'call_started', message: 'Receptionist answered', created_at: '2026-10-24T07:00:00Z' },
  {
    type: 'appointment_booked',
    message: 'Booked K7M2QX: Dr. Aditi Deshmukh',
    created_at: '2026-10-24T07:00:09Z',
  },
]

describe('mergeTimeline', () => {
  it('interleaves turns and events in the order they happened', () => {
    const items = mergeTimeline(TURNS, EVENTS)

    expect(items.map((item) => (item.kind === 'turn' ? item.turn.text : item.event.message))).toEqual([
      'Receptionist answered',
      'Thank you for calling.',
      'Book me with Dr. Deshmukh.',
      'Booked K7M2QX: Dr. Aditi Deshmukh',
    ])
  })
})

describe('CallTimeline', () => {
  it('shows the conversation with the events between turns', () => {
    render(<CallTimeline turns={TURNS} events={EVENTS} activity={null} live={false} />)

    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(4)
    expect(items[1]).toHaveTextContent('ReceptionistThank you for calling.')
    expect(items[3]).toHaveTextContent('Booked K7M2QX: Dr. Aditi Deshmukh')
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('says who is talking while the call is live', () => {
    render(<CallTimeline turns={TURNS} events={[]} activity="agent_thinking" live />)

    expect(screen.getByRole('status')).toHaveTextContent('Receptionist is thinking…')
  })
})
