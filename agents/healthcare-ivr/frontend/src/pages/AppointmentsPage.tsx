import { Link, useSearchParams } from 'react-router'

import { useAppointments, useSetAppointmentStatus } from '../api/queries'
import type { Appointment, AppointmentScope, AppointmentStatus } from '../api/types'
import { AppointmentStatusBadge } from '../components/AppointmentStatusBadge'
import { ageAndGender } from '../utils/appointments'
import { formatClock, formatLocalDate } from '../utils/format'

const SCOPES: { scope: AppointmentScope; label: string }[] = [
  { scope: 'upcoming', label: 'Upcoming' },
  { scope: 'past', label: 'Past' },
]

function todayIso(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${String(now.getDate()).padStart(2, '0')}`
}

/** The outcomes staff can record for an appointment in its current state. */
function actionsFor(appointment: Appointment): { label: string; status: AppointmentStatus }[] {
  switch (appointment.status) {
    case 'booked':
      return [
        ...(appointment.appointment_date <= todayIso()
          ? [
              { label: 'Attended', status: 'completed' as const },
              { label: 'No-show', status: 'no_show' as const },
            ]
          : []),
        { label: 'Cancel', status: 'cancelled' },
      ]
    case 'completed':
    case 'no_show':
      return [{ label: 'Undo', status: 'booked' }]
    case 'cancelled':
      return []
  }
}

export function AppointmentsPage() {
  const [searchParams] = useSearchParams()
  const scope: AppointmentScope = searchParams.get('scope') === 'past' ? 'past' : 'upcoming'
  const { data, error, isPending } = useAppointments(scope)
  const setStatus = useSetAppointmentStatus()

  function record(appointment: Appointment, status: AppointmentStatus) {
    if (
      status === 'cancelled' &&
      !window.confirm(`Cancel appointment ${appointment.reference} for ${appointment.patient_name}?`)
    ) {
      return
    }
    setStatus.mutate({ id: appointment.id, status })
  }

  return (
    <>
      <title>Appointments – Hospital Reception IVR</title>
      <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Appointments</h1>
      <p className="mt-1 text-ink-muted">
        Outpatient appointments the receptionist booked on calls. Mark visits as attended to count
        their revenue.
      </p>

      <nav aria-label="Appointment dates" className="mt-6 flex gap-1">
        {SCOPES.map((item) => (
          <Link
            key={item.scope}
            to={item.scope === 'upcoming' ? '/appointments' : '/appointments?scope=past'}
            aria-current={item.scope === scope ? 'page' : undefined}
            className={`rounded-md px-3 py-1.5 text-sm font-semibold ${
              item.scope === scope ? 'bg-surface-muted text-ink' : 'text-ink-muted hover:text-ink'
            }`}
          >
            {item.label}
          </Link>
        ))}
      </nav>

      {isPending && <p className="mt-6 text-ink-muted">Loading appointments…</p>}

      {setStatus.isError && (
        <p role="alert" className="mt-4 rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm">
          Couldn’t update the appointment. {setStatus.error.message}
        </p>
      )}

      {error && (
        <p role="alert" className="mt-6 rounded-lg border border-line bg-surface px-4 py-3">
          Couldn’t load appointments. {error.message}
        </p>
      )}

      {data && data.items.length === 0 && (
        <div className="mt-4 rounded-xl border border-dashed border-line bg-surface px-6 py-12 text-center">
          <h2 className="text-lg font-semibold">
            {scope === 'upcoming' ? 'No upcoming appointments' : 'No past appointments'}
          </h2>
          <p className="mx-auto mt-2 max-w-prose text-ink-muted">
            When a caller agrees to book, the receptionist saves the appointment and it appears here.
          </p>
        </div>
      )}

      {data && data.items.length > 0 && (
        // `relative` keeps the absolutely positioned sr-only header inside the scroll area.
        <div className="relative mt-4 overflow-x-auto rounded-xl border border-line bg-surface">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line text-ink-muted">
              <tr>
                <th scope="col" className="px-4 py-3 font-medium sm:px-5">When</th>
                <th scope="col" className="px-4 py-3 font-medium">Doctor</th>
                <th scope="col" className="px-4 py-3 font-medium">Patient</th>
                <th scope="col" className="px-4 py-3 font-medium">Reference</th>
                <th scope="col" className="px-4 py-3 font-medium">Status</th>
                <th scope="col" className="px-4 py-3 font-medium sm:px-5">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data.items.map((appointment) => (
                <tr key={appointment.id} className="align-top">
                  <td className="px-4 py-3 whitespace-nowrap sm:px-5">
                    <p className="font-semibold">{formatLocalDate(appointment.appointment_date)}</p>
                    <p className="text-ink-muted tabular-nums">{formatClock(appointment.start_time)}</p>
                  </td>
                  <td className="px-4 py-3">
                    <p className="whitespace-nowrap">{appointment.doctor_name}</p>
                    <p className="text-ink-muted">{appointment.department}</p>
                  </td>
                  <td className="px-4 py-3">
                    <p>{appointment.patient_name}</p>
                    {ageAndGender(appointment) && (
                      <p className="text-ink-muted">{ageAndGender(appointment)}</p>
                    )}
                    <p className="text-ink-muted whitespace-nowrap">{appointment.patient_phone}</p>
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-semibold tracking-wider">{appointment.reference}</span>
                    {appointment.call_id && (
                      <p>
                        <Link
                          to={`/calls/${appointment.call_id}`}
                          className="text-ink-muted underline-offset-4 hover:text-ink hover:underline"
                        >
                          View call
                        </Link>
                      </p>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <AppointmentStatusBadge status={appointment.status} />
                  </td>
                  <td className="px-4 py-3 text-right whitespace-nowrap sm:px-5">
                    <div className="flex justify-end gap-1">
                      {actionsFor(appointment).map((action) => (
                        <button
                          key={action.status}
                          type="button"
                          aria-label={`${action.label} ${appointment.reference}`}
                          disabled={setStatus.isPending}
                          onClick={() => record(appointment, action.status)}
                          className={`rounded-md border border-line px-2.5 py-1 text-xs font-semibold hover:bg-surface-muted disabled:opacity-60 ${
                            action.status === 'cancelled' ? 'text-danger' : 'text-ink'
                          }`}
                        >
                          {action.label}
                        </button>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
