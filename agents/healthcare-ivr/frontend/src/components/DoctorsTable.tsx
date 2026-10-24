import type { Doctor } from '../api/types'
import { formatInr } from '../utils/format'

export function DoctorsTable({ doctors }: { doctors: Doctor[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-line text-ink-muted">
          <tr>
            <th scope="col" className="py-2 pr-4 font-medium">Doctor</th>
            <th scope="col" className="py-2 pr-4 font-medium">Speciality</th>
            <th scope="col" className="py-2 pr-4 font-medium">OPD days</th>
            <th scope="col" className="py-2 pr-4 font-medium">OPD hours</th>
            <th scope="col" className="py-2 text-right font-medium">Fee</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {doctors.map((doctor) => (
            <tr key={doctor.id} className="align-top">
              <td className="py-2.5 pr-4">
                <p className="font-semibold whitespace-nowrap">{doctor.name}</p>
                {doctor.specialty && <p className="text-ink-muted">{doctor.specialty}</p>}
              </td>
              <td className="py-2.5 pr-4">{doctor.department}</td>
              <td className="py-2.5 pr-4">{doctor.opd_days}</td>
              <td className="py-2.5 pr-4 whitespace-nowrap">{doctor.opd_hours}</td>
              <td className="py-2.5 text-right tabular-nums whitespace-nowrap">
                {formatInr(doctor.consultation_fee_inr)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
