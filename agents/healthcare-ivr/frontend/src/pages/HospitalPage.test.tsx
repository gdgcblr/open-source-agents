import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { AnalyticsSummary, Doctor, HospitalInfo } from '../api/types'
import { mockFetch } from '../test/mockFetch'
import { HospitalPage } from './HospitalPage'

const MARKDOWN = `# Sahyadri Hospital

## Timings

| Service | Days | Hours |
| --- | --- | --- |
| Outpatient consultations (OPD) | Monday to Saturday | 9:00 AM to 6:00 PM |
`

const DOCTOR: Doctor = {
  id: 'dr-aditi-deshmukh',
  name: 'Dr. Aditi Deshmukh',
  department: 'Cardiology',
  specialty: 'Preventive cardiology',
  opd_weekdays: [0, 2, 4],
  opd_start: '09:00:00',
  opd_end: '13:00:00',
  slot_minutes: 15,
  consultation_fee_inr: 1200,
  opd_days: 'Monday, Wednesday, Friday',
  opd_hours: '9:00 AM to 1:00 PM',
}
const HOSPITAL: HospitalInfo = { name: 'Sahyadri Hospital', markdown: MARKDOWN, doctors: [DOCTOR] }

const SUMMARY: AnalyticsSummary = {
  period_days: 30,
  phone_calls: 40,
  calls_by_language: { en: 31, hi: 9 },
  voice_agent_minutes: 96.5,
  ai_cost_usd: 15.73,
  appointments_booked: 18,
  appointments_completed: 12,
  appointments_no_show: 3,
  appointments_cancelled: 1,
  appointments_pending: 2,
  revenue_inr: 14400,
  booking_rate: 0.45,
  completion_rate: 0.8,
  cost_per_booking_usd: 0.8739,
  cost_per_completed_usd: 1.3108,
}

function renderPage(routes: Record<string, unknown> = {}) {
  const fetchMock = mockFetch({
    '/api/hospital': HOSPITAL,
    '/api/analytics/summary': SUMMARY,
    ...routes,
  })
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <HospitalPage />
    </QueryClientProvider>,
  )
  return fetchMock
}

describe('HospitalPage', () => {
  it('shows the information, doctors and outline', async () => {
    renderPage()

    expect(await screen.findByRole('heading', { level: 1, name: 'Sahyadri Hospital' })).toBeInTheDocument()
    const doctors = screen.getByRole('region', { name: 'Doctors and OPD schedule' })
    const row = within(doctors).getByRole('row', { name: /Dr. Aditi Deshmukh/ })
    expect(within(row).getByText('₹1,200')).toBeInTheDocument()
    const outline = screen.getByRole('navigation', { name: 'On this page' })
    expect(within(outline).getByRole('link', { name: 'Timings' })).toHaveAttribute('href', '#timings')
    expect(screen.getByRole('heading', { level: 2, name: 'Timings' })).toHaveAttribute('id', 'timings')
  })

  it('shows spend and the calls → bookings → attended funnel', async () => {
    const fetchMock = renderPage()

    const performance = await screen.findByRole('region', { name: 'Performance' })
    expect(await within(performance).findByText('Calls handled')).toBeInTheDocument()
    expect(within(performance).getByText('45% of calls')).toBeInTheDocument()
    expect(within(performance).getByText('80% of visits with a recorded outcome')).toBeInTheDocument()
    expect(within(performance).getByText('$15.73')).toBeInTheDocument()
    expect(within(performance).getByText('₹14,400')).toBeInTheDocument()
    expect(within(performance).getByText('96.5 voice-agent minutes')).toBeInTheDocument()
    expect(within(performance).getByText('Calls in Hindi').nextSibling).toHaveTextContent('9')

    await userEvent.click(within(performance).getByRole('button', { name: 'All time' }))
    expect(fetchMock).toHaveBeenCalledWith('/api/analytics/summary?days=0', undefined)
  })

  it('saves edited information', async () => {
    const fetchMock = renderPage({
      'PUT /api/hospital/info': { ...HOSPITAL, markdown: '# Sahyadri Hospital\n\nOPD closed on Diwali.\n' },
    })

    await userEvent.click(await screen.findByRole('button', { name: 'Edit information' }))
    const editor = screen.getByLabelText('Information (Markdown)')
    await userEvent.clear(editor)
    await userEvent.type(editor, '# Sahyadri Hospital{enter}{enter}OPD closed on Diwali.')
    await userEvent.click(screen.getByRole('button', { name: 'Save information' }))

    expect(fetchMock).toHaveBeenCalledWith('/api/hospital/info', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: 'Sahyadri Hospital',
        markdown: '# Sahyadri Hospital\n\nOPD closed on Diwali.',
      }),
    })
    expect(await screen.findByText('OPD closed on Diwali.')).toBeInTheDocument()
  })

  it('explains why a save was rejected', async () => {
    renderPage({
      'PUT /api/hospital/info': () => Response.json({ detail: 'The hospital needs a name.' }, { status: 422 }),
    })

    await userEvent.click(await screen.findByRole('button', { name: 'Edit information' }))
    await userEvent.clear(screen.getByLabelText('Hospital name'))
    await userEvent.click(screen.getByRole('button', { name: 'Save information' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('The hospital needs a name.')
  })

  it('adds a doctor to the roster', async () => {
    const fetchMock = renderPage({ 'PUT /api/hospital/doctors': HOSPITAL })

    await userEvent.click(await screen.findByRole('button', { name: 'Edit doctors' }))
    await userEvent.click(screen.getByRole('button', { name: 'Add doctor' }))
    await userEvent.type(screen.getByLabelText('Name', { selector: '#doctor-1-name' }), 'Dr. New Joiner')
    await userEvent.type(screen.getByLabelText('Speciality', { selector: '#doctor-1-department' }), 'Neurology')
    await userEvent.click(screen.getByRole('button', { name: 'Save doctors' }))

    const [, init] = fetchMock.mock.calls.find(([url]) => url === '/api/hospital/doctors')!
    const sent = JSON.parse(String(init?.body)).doctors
    expect(sent).toHaveLength(2)
    expect(sent[0]).toMatchObject({ id: 'dr-aditi-deshmukh', opd_start: '09:00', opd_end: '13:00' })
    expect(sent[1]).toMatchObject({ id: '', name: 'Dr. New Joiner', department: 'Neurology' })
  })
})
