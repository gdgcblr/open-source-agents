import { useState, type FormEvent } from 'react'

import { useUpdateDoctors } from '../api/queries'
import type { Doctor, DoctorInput } from '../api/types'
import { buttonStyles } from '../utils/ui'

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

const inputClass = 'w-full rounded-md border border-line bg-surface px-2.5 py-1.5 text-sm text-ink'

function toInput(doctor: Doctor): DoctorInput {
  return {
    id: doctor.id,
    name: doctor.name,
    department: doctor.department,
    specialty: doctor.specialty,
    opd_weekdays: doctor.opd_weekdays,
    opd_start: doctor.opd_start.slice(0, 5),
    opd_end: doctor.opd_end.slice(0, 5),
    slot_minutes: doctor.slot_minutes,
    consultation_fee_inr: doctor.consultation_fee_inr,
  }
}

const NEW_DOCTOR: DoctorInput = {
  id: '',
  name: '',
  department: '',
  specialty: '',
  opd_weekdays: [0, 1, 2, 3, 4, 5],
  opd_start: '09:00',
  opd_end: '13:00',
  slot_minutes: 15,
  consultation_fee_inr: null,
}

interface DoctorsEditorProps {
  doctors: Doctor[]
  onDone: () => void
}

export function DoctorsEditor({ doctors, onDone }: DoctorsEditorProps) {
  const [rows, setRows] = useState<DoctorInput[]>(() => doctors.map(toInput))
  const save = useUpdateDoctors()

  function update(index: number, changes: Partial<DoctorInput>) {
    setRows((current) => current.map((row, i) => (i === index ? { ...row, ...changes } : row)))
  }

  function toggleDay(index: number, day: number) {
    const days = rows[index].opd_weekdays
    update(index, {
      opd_weekdays: days.includes(day) ? days.filter((d) => d !== day) : [...days, day].sort((a, b) => a - b),
    })
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    save.mutate(rows, { onSuccess: onDone })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <ol className="space-y-3">
        {rows.map((row, index) => {
          const label = row.name || `Doctor ${index + 1}`
          const field = (name: string) => `doctor-${index}-${name}`
          return (
            <li key={row.id || `new-${index}`} className="rounded-lg border border-line p-4">
              <fieldset>
                <legend className="sr-only">{label}</legend>
                <div className="grid gap-3 sm:grid-cols-3">
                  <div>
                    <label htmlFor={field('name')} className="text-xs font-semibold text-ink-muted">Name</label>
                    <input id={field('name')} value={row.name} onChange={(e) => update(index, { name: e.target.value })} className={inputClass} required />
                  </div>
                  <div>
                    <label htmlFor={field('department')} className="text-xs font-semibold text-ink-muted">Speciality</label>
                    <input id={field('department')} value={row.department} onChange={(e) => update(index, { department: e.target.value })} className={inputClass} required />
                  </div>
                  <div>
                    <label htmlFor={field('specialty')} className="text-xs font-semibold text-ink-muted">Focus</label>
                    <input id={field('specialty')} value={row.specialty} onChange={(e) => update(index, { specialty: e.target.value })} className={inputClass} />
                  </div>
                </div>

                <div className="mt-3 flex flex-wrap items-end gap-x-5 gap-y-3">
                  <div>
                    <p className="text-xs font-semibold text-ink-muted">OPD days</p>
                    <div role="group" aria-label={`${label} OPD days`} className="mt-1 flex gap-1">
                      {WEEKDAYS.map((day, dayIndex) => {
                        const on = row.opd_weekdays.includes(dayIndex)
                        return (
                          <button
                            key={day}
                            type="button"
                            aria-pressed={on}
                            onClick={() => toggleDay(index, dayIndex)}
                            className={`rounded-md border px-2 py-1 text-xs font-semibold ${
                              on ? 'border-ink bg-ink text-page' : 'border-line text-ink-muted hover:text-ink'
                            }`}
                          >
                            {day}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                  <div className="w-28">
                    <label htmlFor={field('start')} className="text-xs font-semibold text-ink-muted">From</label>
                    <input id={field('start')} type="time" value={row.opd_start} onChange={(e) => update(index, { opd_start: e.target.value })} className={inputClass} required />
                  </div>
                  <div className="w-28">
                    <label htmlFor={field('end')} className="text-xs font-semibold text-ink-muted">To</label>
                    <input id={field('end')} type="time" value={row.opd_end} onChange={(e) => update(index, { opd_end: e.target.value })} className={inputClass} required />
                  </div>
                  <div className="w-24">
                    <label htmlFor={field('slot')} className="text-xs font-semibold text-ink-muted">Slot (min)</label>
                    <input id={field('slot')} type="number" min={5} max={240} value={row.slot_minutes} onChange={(e) => update(index, { slot_minutes: Number(e.target.value) })} className={inputClass} required />
                  </div>
                  <div className="w-28">
                    <label htmlFor={field('fee')} className="text-xs font-semibold text-ink-muted">Fee (₹)</label>
                    <input
                      id={field('fee')}
                      type="number"
                      min={0}
                      value={row.consultation_fee_inr ?? ''}
                      onChange={(e) =>
                        update(index, { consultation_fee_inr: e.target.value === '' ? null : Number(e.target.value) })
                      }
                      className={inputClass}
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => setRows((current) => current.filter((_, i) => i !== index))}
                    className="ml-auto text-sm font-semibold text-danger hover:underline"
                  >
                    Remove <span className="sr-only">{label}</span>
                  </button>
                </div>
              </fieldset>
            </li>
          )
        })}
      </ol>

      <button
        type="button"
        className={buttonStyles.secondary}
        onClick={() => setRows((current) => [...current, { ...NEW_DOCTOR }])}
      >
        Add doctor
      </button>

      {save.isError && (
        <p role="alert" className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm">
          Couldn’t save. {save.error.message}
        </p>
      )}

      <div className="flex gap-2">
        <button type="submit" className={buttonStyles.primary} disabled={save.isPending}>
          {save.isPending ? 'Saving…' : 'Save doctors'}
        </button>
        <button type="button" className={buttonStyles.secondary} onClick={onDone}>
          Cancel
        </button>
      </div>
    </form>
  )
}
