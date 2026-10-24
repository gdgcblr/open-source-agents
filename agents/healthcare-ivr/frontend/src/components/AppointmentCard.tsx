import type { Appointment } from '../api/types'
import { ageAndGender } from '../utils/appointments'
import { formatClock, formatLocalDate } from '../utils/format'
import { AppointmentStatusBadge } from './AppointmentStatusBadge'

export function AppointmentCard({ appointment }: { appointment: Appointment }) {
  return (
    <section
      aria-label={`Appointment ${appointment.reference}`}
      className="rounded-xl border border-line bg-surface p-4 sm:p-5"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-semibold">
          <AppointmentStatusBadge status={appointment.status} />
          <span className="sr-only"> appointment</span>
        </h2>
        <p className="text-sm text-ink-muted">
          Reference <span className="font-semibold tracking-wider text-ink">{appointment.reference}</span>
        </p>
      </div>
      <dl className="mt-3 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-sm">
        <dt className="text-ink-muted">Doctor</dt>
        <dd>
          {appointment.doctor_name}, {appointment.department}
        </dd>
        <dt className="text-ink-muted">When</dt>
        <dd>
          {formatLocalDate(appointment.appointment_date)} at {formatClock(appointment.start_time)}
        </dd>
        <dt className="text-ink-muted">Patient</dt>
        <dd>{[appointment.patient_name, ageAndGender(appointment)].filter(Boolean).join(', ')}</dd>
        <dt className="text-ink-muted">Phone</dt>
        <dd>{appointment.patient_phone}</dd>
        {appointment.symptoms && (
          <>
            <dt className="text-ink-muted">Symptoms</dt>
            <dd>{appointment.symptoms}</dd>
          </>
        )}
      </dl>
    </section>
  )
}
