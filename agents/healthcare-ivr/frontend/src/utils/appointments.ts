import type { Appointment } from '../api/types'

const GENDER_LABELS: Record<string, string> = {
  female: 'female',
  male: 'male',
  other: 'other gender',
  prefer_not_to_say: 'gender not given',
}

/** "42, female": the patient's age and gender as collected on the call, whichever were given. */
export function ageAndGender(appointment: Appointment): string {
  const parts: string[] = []
  if (appointment.patient_age !== null) parts.push(String(appointment.patient_age))
  if (appointment.patient_gender) {
    parts.push(GENDER_LABELS[appointment.patient_gender] ?? appointment.patient_gender)
  }
  return parts.join(', ')
}
