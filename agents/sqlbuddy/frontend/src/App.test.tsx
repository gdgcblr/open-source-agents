import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'

vi.mock('./api', () => ({
  ApiError: class ApiError extends Error {},
  api: {
    listSessions: vi.fn().mockResolvedValue([]),
    createQuery: vi.fn(),
    getSession: vi.fn(),
    renameSession: vi.fn(),
    deleteSession: vi.fn(),
  },
}))

import { api } from './api'

describe('SQLBuddy web form', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows the form, database choices, and empty state', async () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: 'SQL, clearly.' })).toBeInTheDocument()
    expect(screen.getByLabelText('DATABASE TYPE')).toHaveValue('sqlite')
    expect(screen.getByText('Your next query starts here')).toBeInTheDocument()
    await waitFor(() => expect(api.listSessions).toHaveBeenCalled())
  })

  it('validates a blank question before making a request', async () => {
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: /Ask SQLBuddy/ }))
    expect(screen.getByRole('alert')).toHaveTextContent('Type a question')
    expect(api.createQuery).not.toHaveBeenCalled()
  })

  it('validates uploaded schema JSON locally', async () => {
    render(<App />)
    const fileInput = screen.getByLabelText('Load schema JSON file') as HTMLInputElement
    const file = new File(['{"wrong":[]}'], 'schema.json', { type: 'application/json' })
    Object.defineProperty(file, 'text', { value: async () => '{"wrong":[]}' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    expect(await screen.findByRole('alert')).toHaveTextContent('Schema JSON must have a "tables" list')
    expect(api.createQuery).not.toHaveBeenCalled()
  })

  it('renders a successful answer and stores the new session', async () => {
    vi.mocked(api.createQuery).mockResolvedValue({
      session_id: 'session-1', dialect: 'postgresql', created_at: new Date().toISOString(),
      answer: { sql: 'SELECT 1;', explanation: 'Returns one row.', assumptions: ['A test assumption.'], risks: ['Check the table name.'], unverified: true },
    })
    render(<App />)
    await userEvent.type(screen.getByLabelText('WHAT WOULD YOU LIKE TO QUERY?'), 'Show one row')
    await userEvent.selectOptions(screen.getByLabelText('DATABASE TYPE'), 'postgresql')
    await userEvent.click(screen.getByRole('button', { name: /Ask SQLBuddy/ }))
    expect(await screen.findByText('SELECT 1;')).toBeInTheDocument()
    expect(screen.getByText('Returns one row.')).toBeInTheDocument()
    expect(screen.getByText('A test assumption.')).toBeInTheDocument()
    expect(screen.getByText('Check the table name.')).toBeInTheDocument()
    expect(api.createQuery).toHaveBeenCalledWith('Show one row', 'postgresql', null, undefined)
  })

  it('shows API errors in plain language', async () => {
    vi.mocked(api.createQuery).mockRejectedValue(new Error('Backend is unavailable.'))
    render(<App />)
    await userEvent.type(screen.getByLabelText('WHAT WOULD YOU LIKE TO QUERY?'), 'Show users')
    await userEvent.click(screen.getByRole('button', { name: /Ask SQLBuddy/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Something went wrong')
  })

  it('reopens a saved session and restores its latest question and answer', async () => {
    const savedSession = { id: 'saved-1', title: 'Recent orders', dialect: 'mysql' as const, updated_at: new Date().toISOString() }
    vi.mocked(api.listSessions)
      .mockResolvedValueOnce([savedSession])
      .mockResolvedValueOnce([{ ...savedSession, title: 'Renamed orders' }])
      .mockResolvedValueOnce([])
    vi.mocked(api.getSession).mockResolvedValue({
      id: 'saved-1', title: 'Recent orders', dialect: 'mysql', updated_at: new Date().toISOString(),
      messages: [{
        question: 'Show recent orders', dialect: 'mysql', created_at: new Date().toISOString(),
        answer: { sql: 'SELECT * FROM orders;', explanation: 'Shows orders.', assumptions: [], risks: [], unverified: true },
      }],
    })
    render(<App />)
    await userEvent.click(await screen.findByTitle('Recent orders'))
    expect(await screen.findByText('SELECT * FROM orders;')).toBeInTheDocument()
    expect(screen.getByLabelText('WHAT WOULD YOU LIKE TO QUERY?')).toHaveValue('Show recent orders')
    expect(screen.getByRole('status')).toHaveTextContent('Opened “Recent orders”.')

    vi.spyOn(window, 'prompt').mockReturnValue('Renamed orders')
    await userEvent.click(screen.getByLabelText('Options for Recent orders'))
    await userEvent.click(screen.getByRole('button', { name: 'Rename' }))
    await waitFor(() => expect(api.renameSession).toHaveBeenCalledWith('saved-1', 'Renamed orders'))
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    await userEvent.click(screen.getByLabelText('Options for Renamed orders'))
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(api.deleteSession).toHaveBeenCalledWith('saved-1'))
    expect(screen.getByText('Your saved questions will appear here.')).toBeInTheDocument()
  })
})
