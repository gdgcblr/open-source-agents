import type { AppointmentStatus } from '../api/types'

const STATUS: Record<AppointmentStatus, { label: string; dot: string }> = {
  booked: { label: 'Booked', dot: 'bg-ink' },
  completed: { label: 'Attended', dot: 'bg-ok' },
  no_show: { label: 'No-show', dot: 'bg-danger' },
  cancelled: { label: 'Cancelled', dot: 'bg-ink-muted' },
}

export function AppointmentStatusBadge({ status }: { status: AppointmentStatus }) {
  const { label, dot } = STATUS[status]
  return (
    <span className="inline-flex items-center gap-2 whitespace-nowrap">
      <span aria-hidden="true" className={`size-2 rounded-full ${dot}`} />
      {label}
    </span>
  )
}
