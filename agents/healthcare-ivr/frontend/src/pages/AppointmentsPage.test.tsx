import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import type { Appointment } from '../api/types'
import { mockFetch } from '../test/mockFetch'
import { AppointmentsPage } from './AppointmentsPage'

const UPCOMING: Appointment = {
  id: 'apt-1',
  reference: 'K7M2QX',
  call_id: 'call-1',
  doctor_name: 'Dr. Aditi Deshmukh',
  department: 'Cardiology',
  appointment_date: '2099-10-26',
  start_time: '09:15:00',
  patient_name: 'Ravi Kumar',
  patient_phone: '+919811122233',
  patient_age: 42,
  patient_gender: 'male',
  symptoms: 'Chest tightness when climbing stairs',
  consultation_fee_inr: 1200,
  status: 'booked',
  status_updated_at: null,
  created_at: '2026-10-24T07:30:00Z',
}
const YESTERDAY: Appointment = { ...UPCOMING, id: 'apt-2', reference: 'P4R8TW', appointment_date: '2026-01-05' }

function renderPage(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <AppointmentsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('AppointmentsPage', () => {
  it('lists upcoming appointments with their status and call', async () => {
    const fetchMock = mockFetch({ '/api/appointments': { items: [UPCOMING] } })

    renderPage('/appointments')

    const row = await screen.findByRole('row', { name: /K7M2QX/ })
    expect(within(row).getByText('Mon, 26 Oct 2099')).toBeInTheDocument()
    expect(within(row).getByText('9:15 AM')).toBeInTheDocument()
    expect(within(row).getByText('42, male')).toBeInTheDocument()
    expect(within(row).getByText('Booked')).toBeInTheDocument()
    expect(within(row).getByRole('link', { name: 'View call' })).toHaveAttribute('href', '/calls/call-1')
    // A future visit can be cancelled but not yet marked attended.
    expect(within(row).getByRole('button', { name: 'Cancel K7M2QX' })).toBeInTheDocument()
    expect(within(row).queryByRole('button', { name: /Attended/ })).not.toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/appointments?scope=upcoming', undefined)
  })

  it('records that a patient attended', async () => {
    const fetchMock = mockFetch({
      '/api/appointments': { items: [YESTERDAY] },
      'PATCH /api/appointments/apt-2': { ...YESTERDAY, status: 'completed' },
    })
    renderPage('/appointments?scope=past')

    await userEvent.click(await screen.findByRole('button', { name: 'Attended P4R8TW' }))

    expect(fetchMock).toHaveBeenCalledWith('/api/appointments/apt-2', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'completed' }),
    })
  })

  it('asks before cancelling', async () => {
    const fetchMock = mockFetch({ '/api/appointments': { items: [UPCOMING] } })
    vi.stubGlobal('confirm', vi.fn(() => false))
    renderPage('/appointments')

    await userEvent.click(await screen.findByRole('button', { name: 'Cancel K7M2QX' }))

    expect(window.confirm).toHaveBeenCalledWith('Cancel appointment K7M2QX for Ravi Kumar?')
    expect(fetchMock).not.toHaveBeenCalledWith('/api/appointments/apt-1', expect.anything())
  })

  it('shows past appointments when asked', async () => {
    const fetchMock = mockFetch({ '/api/appointments': { items: [] } })

    renderPage('/appointments?scope=past')

    expect(await screen.findByRole('heading', { name: 'No past appointments' })).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/appointments?scope=past', undefined)
  })
})
