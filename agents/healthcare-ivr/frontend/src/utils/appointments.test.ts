import { describe, expect, it } from 'vitest'

import type { Appointment } from '../api/types'
import { ageAndGender } from './appointments'

const APPOINTMENT = { patient_age: 42, patient_gender: 'female' } as Appointment

describe('ageAndGender', () => {
  it('joins whichever details were given', () => {
    expect(ageAndGender(APPOINTMENT)).toBe('42, female')
    expect(ageAndGender({ ...APPOINTMENT, patient_gender: 'prefer_not_to_say' })).toBe('42, gender not given')
    expect(ageAndGender({ ...APPOINTMENT, patient_age: null, patient_gender: null })).toBe('')
  })
})
