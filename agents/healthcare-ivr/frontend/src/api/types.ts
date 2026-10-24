// Mirrors the Pydantic response models in backend/app/schemas.py.

export type CallSource = 'phone' | 'upload'
export type CallStatus = 'in_progress' | 'completed'
export type DiarizationStatus = 'pending' | 'processing' | 'completed' | 'failed' | 'skipped'
export type SpeakerRole = 'agent' | 'customer'
export type AppointmentStatus = 'booked' | 'completed' | 'no_show' | 'cancelled'
export type AppointmentScope = 'upcoming' | 'past'

export interface CallSummary {
  id: string
  source: CallSource
  status: CallStatus
  title: string | null
  caller_number: string | null
  called_number: string | null
  language: string | null // "en" or "hi" while the receptionist speaks it
  started_at: string
  ended_at: string | null
  duration_seconds: number | null
  diarization_status: DiarizationStatus
  speaker_count: number | null
  has_audio: boolean
  agent_seconds: number | null
  agent_cost_usd: number | null
  transcription_cost_usd: number | null
  total_cost_usd: number | null
}

export interface TranscriptTurn {
  role: SpeakerRole
  text: string
  created_at: string
}

export interface Utterance {
  speaker: number
  start: number
  end: number
  text: string
  confidence: number
}

export type CallEventType =
  | 'call_started'
  | 'language_changed'
  | 'language_not_supported'
  | 'recording_started'
  | 'recording_failed'
  | 'availability_checked'
  | 'appointment_booked'
  | 'appointments_looked_up'
  | 'appointment_cancelled'
  | 'appointment_completed'
  | 'appointment_no_show'
  | 'tool_error'
  | 'agent_error'
  | 'time_limit_reached'
  | 'agent_ended_call'
  | 'call_ended'
  | 'recording_received'
  | 'transcription_completed'
  | 'transcription_failed'

export interface CallEvent {
  type: CallEventType
  message: string
  created_at: string
}

export interface Appointment {
  id: string
  reference: string
  call_id: string | null
  doctor_name: string
  department: string
  appointment_date: string // YYYY-MM-DD, hospital local date
  start_time: string // HH:MM:SS, hospital local time
  patient_name: string
  patient_phone: string
  patient_age: number | null
  patient_gender: string | null // female, male, other or prefer_not_to_say
  symptoms: string | null
  consultation_fee_inr: number | null
  status: AppointmentStatus
  status_updated_at: string | null
  created_at: string
}

export interface CallDetail extends CallSummary {
  diarization_error: string | null
  turns: TranscriptTurn[]
  utterances: Utterance[]
  appointments: Appointment[]
  events: CallEvent[]
}

export interface LiveCall extends CallSummary {
  latest_turn: TranscriptTurn | null
}

export interface LiveCallList {
  items: LiveCall[]
}

/** A roster row as the editor sends it; `id` is empty for a new doctor. */
export interface DoctorInput {
  id: string
  name: string
  department: string
  specialty: string
  opd_weekdays: number[] // Monday is 0
  opd_start: string // HH:MM
  opd_end: string // HH:MM
  slot_minutes: number
  consultation_fee_inr: number | null
}

export interface Doctor extends DoctorInput {
  opd_days: string // e.g. "Monday, Wednesday, Friday"
  opd_hours: string // e.g. "9:00 AM to 1:00 PM"
}

export interface HospitalInfo {
  name: string
  markdown: string
  doctors: Doctor[]
}

export interface AppointmentList {
  items: Appointment[]
}

export interface AnalyticsSummary {
  period_days: number | null
  phone_calls: number
  calls_by_language: Record<string, number>
  voice_agent_minutes: number
  ai_cost_usd: number
  appointments_booked: number
  appointments_completed: number
  appointments_no_show: number
  appointments_cancelled: number
  appointments_pending: number
  revenue_inr: number
  booking_rate: number | null
  completion_rate: number | null
  cost_per_booking_usd: number | null
  cost_per_completed_usd: number | null
}

export interface CallPage {
  items: CallSummary[]
  total: number
  page: number
  page_size: number
  total_cost_usd: number
}
