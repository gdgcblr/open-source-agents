import type {
  AnalyticsSummary,
  Appointment,
  AppointmentList,
  AppointmentScope,
  AppointmentStatus,
  CallDetail,
  CallPage,
  CallSummary,
  DoctorInput,
  HospitalInfo,
  LiveCallList,
} from './types'

const API_BASE = '/api'

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function errorMessage(response: Response): Promise<string> {
  if (response.status === 401) {
    return 'Sign in with the dashboard username and password to see calls.'
  }
  try {
    const body: unknown = await response.json()
    if (body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string') {
      return body.detail
    }
  } catch {
    // Not a JSON error body; fall through to the generic message.
  }
  return `Request failed with status ${response.status}.`
}

function jsonBody(method: 'PUT' | 'PATCH', body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init)
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response))
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

export const api = {
  listCalls(page: number, pageSize: number): Promise<CallPage> {
    const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
    return request(`/calls?${query}`)
  },

  listLiveCalls(): Promise<LiveCallList> {
    return request('/calls/live')
  },

  callStreamUrl(callId: string): string {
    return `${API_BASE}/calls/${encodeURIComponent(callId)}/stream`
  },

  getCall(callId: string): Promise<CallDetail> {
    return request(`/calls/${encodeURIComponent(callId)}`)
  },

  uploadRecording(file: File): Promise<CallSummary> {
    const form = new FormData()
    form.append('file', file)
    return request('/calls/upload', { method: 'POST', body: form })
  },

  deleteCall(callId: string): Promise<void> {
    return request(`/calls/${encodeURIComponent(callId)}`, { method: 'DELETE' })
  },

  listAppointments(scope: AppointmentScope): Promise<AppointmentList> {
    return request(`/appointments?${new URLSearchParams({ scope })}`)
  },

  setAppointmentStatus(appointmentId: string, status: AppointmentStatus): Promise<Appointment> {
    return request(`/appointments/${encodeURIComponent(appointmentId)}`, jsonBody('PATCH', { status }))
  },

  getHospitalInfo(): Promise<HospitalInfo> {
    return request('/hospital')
  },

  updateHospitalInfo(name: string, markdown: string): Promise<HospitalInfo> {
    return request('/hospital/info', jsonBody('PUT', { name, markdown }))
  },

  updateDoctors(doctors: DoctorInput[]): Promise<HospitalInfo> {
    return request('/hospital/doctors', jsonBody('PUT', { doctors }))
  },

  getAnalytics(days: number): Promise<AnalyticsSummary> {
    return request(`/analytics/summary?${new URLSearchParams({ days: String(days) })}`)
  },

  audioUrl(callId: string): string {
    return `${API_BASE}/calls/${encodeURIComponent(callId)}/audio`
  },
}
