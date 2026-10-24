import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import type { CallPage, CallSummary, LiveCall } from '../api/types'
import { mockFetch } from '../test/mockFetch'
import { CallsPage } from './CallsPage'

const phoneCall: CallSummary = {
  id: 'call-1',
  source: 'phone',
  status: 'completed',
  title: null,
  caller_number: '+15550100',
  called_number: '+912067215000',
  language: 'en',
  started_at: '2026-10-24T06:30:00Z',
  ended_at: '2026-10-24T06:33:41Z',
  duration_seconds: 221,
  diarization_status: 'completed',
  speaker_count: 2,
  has_audio: true,
  agent_seconds: 221,
  agent_cost_usd: 0.6004,
  transcription_cost_usd: 0.0158,
  total_cost_usd: 0.6162,
}

const liveCall: LiveCall = {
  ...phoneCall,
  id: 'call-live',
  caller_number: '+919811122233',
  language: 'hi',
  status: 'in_progress',
  started_at: new Date(Date.now() - 75_000).toISOString(),
  latest_turn: {
    role: 'customer',
    text: 'I need a cardiologist on Wednesday.',
    created_at: new Date().toISOString(),
  },
}

const EMPTY_PAGE: CallPage = { items: [], total: 0, page: 1, page_size: 20, total_cost_usd: 0 }

function mockCalls(page: CallPage, live: LiveCall[] = []) {
  return mockFetch({ '/api/calls': page, '/api/calls/live': { items: live } })
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <CallsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('CallsPage', () => {
  it('lists calls with their transcript status and cost', async () => {
    const fetchMock = mockCalls({
      items: [phoneCall],
      total: 1,
      page: 1,
      page_size: 20,
      total_cost_usd: 0.6162,
    })

    renderPage()

    const link = await screen.findByRole('link', { name: '+15550100' })
    expect(link).toHaveAttribute('href', '/calls/call-1')
    expect(screen.getByText('3m 41s')).toBeInTheDocument()
    expect(screen.getByText('Ready')).toBeInTheDocument()
    expect(
      screen.getByText('1 call answered by the reception agent, $0.62 in AI costs'),
    ).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: '$0.62' })).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/calls?page=1&page_size=20', undefined)
  })

  it('shows calls happening now at the top', async () => {
    mockCalls(EMPTY_PAGE, [liveCall])

    renderPage()

    const live = await screen.findByRole('region', { name: /Live now/ })
    const card = await within(live).findByRole('link', { name: /\+919811122233/ })
    expect(card).toHaveAttribute('href', '/calls/call-live')
    expect(card).toHaveTextContent('Caller: I need a cardiologist on Wednesday.')
    expect(card).toHaveTextContent('1:15')
    expect(card).toHaveTextContent('Hindi')
  })

  it('says which calls were in Hindi', async () => {
    mockCalls({
      items: [phoneCall, { ...phoneCall, id: 'call-2', caller_number: '+919800000001', language: 'hi' }],
      total: 2,
      page: 1,
      page_size: 20,
      total_cost_usd: 1.23,
    })

    renderPage()

    const hindiRow = await screen.findByRole('row', { name: /\+919800000001/ })
    expect(within(hindiRow).getByText('Phone call in Hindi')).toBeInTheDocument()
    const englishRow = screen.getByRole('row', { name: /\+15550100/ })
    expect(within(englishRow).getByText('Phone call')).toBeInTheDocument()
  })

  it('says when no call is live and none have been made', async () => {
    mockCalls(EMPTY_PAGE)

    renderPage()

    expect(await screen.findByText(/No calls in progress/)).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'No calls yet' })).toBeInTheDocument()
  })

  it('shows sign-in guidance when the dashboard credentials are missing', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(null, { status: 401 })))

    renderPage()

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Sign in with the dashboard username and password',
    )
  })
})
