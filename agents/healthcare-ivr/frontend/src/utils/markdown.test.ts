import { describe, expect, it } from 'vitest'

import { sectionsOf, slugify } from './markdown'

describe('slugify', () => {
  it.each([
    ['Location and contact', 'location-and-contact'],
    ['Insurance and payments', 'insurance-and-payments'],
    ['Obstetrics & Gynaecology (OB/GYN)', 'obstetrics-gynaecology-ob-gyn'],
  ])('turns %s into %s', (heading, expected) => {
    expect(slugify(heading)).toBe(expected)
  })
})

describe('sectionsOf', () => {
  it('lists second-level headings in order and ignores other levels', () => {
    const markdown = '# MedCare\n\n## Timings\n\ntext\n\n### Pharmacy\n\n## Doctors\n'

    expect(sectionsOf(markdown)).toEqual([
      { id: 'timings', title: 'Timings' },
      { id: 'doctors', title: 'Doctors' },
    ])
  })
})
