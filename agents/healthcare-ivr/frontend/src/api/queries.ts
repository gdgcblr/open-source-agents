import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from './client'
import type { AppointmentScope, AppointmentStatus, CallSummary, DoctorInput } from './types'

export const PAGE_SIZE = 20

export const callKeys = {
  all: ['calls'] as const,
  list: (page: number) => [...callKeys.all, 'list', page] as const,
  detail: (callId: string) => [...callKeys.all, 'detail', callId] as const,
}

export const hospitalKeys = {
  info: ['hospital', 'info'] as const,
}

export const appointmentKeys = {
  all: ['appointments'] as const,
  list: (scope: AppointmentScope) => ['appointments', scope] as const,
}

export const liveCallKeys = { all: ['calls', 'live'] as const }

export const analyticsKeys = {
  all: ['analytics'] as const,
  summary: (days: number) => ['analytics', days] as const,
}

/** A call still changing on the server: the line is open or the transcript is being made. */
export function isCallActive(call: CallSummary): boolean {
  return (
    call.status === 'in_progress' ||
    call.diarization_status === 'pending' ||
    call.diarization_status === 'processing'
  )
}

export function useCalls(page: number) {
  return useQuery({
    queryKey: callKeys.list(page),
    queryFn: () => api.listCalls(page, PAGE_SIZE),
    placeholderData: keepPreviousData,
    refetchInterval: (query) => (query.state.data?.items.some(isCallActive) ? 5000 : false),
  })
}

export function useCall(callId: string) {
  return useQuery({
    queryKey: callKeys.detail(callId),
    queryFn: () => api.getCall(callId),
    refetchInterval: (query) =>
      query.state.data && isCallActive(query.state.data) ? 3000 : false,
  })
}

export function useLiveCalls() {
  return useQuery({
    queryKey: liveCallKeys.all,
    queryFn: () => api.listLiveCalls(),
    refetchInterval: 3000,
  })
}

export function useAnalytics(days: number) {
  return useQuery({
    queryKey: analyticsKeys.summary(days),
    queryFn: () => api.getAnalytics(days),
    placeholderData: keepPreviousData,
  })
}

export function useSetAppointmentStatus() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: AppointmentStatus }) =>
      api.setAppointmentStatus(id, status),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: appointmentKeys.all }),
        queryClient.invalidateQueries({ queryKey: analyticsKeys.all }),
        queryClient.invalidateQueries({ queryKey: callKeys.all }),
      ]),
  })
}

export function useUpdateHospitalInfo() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ name, markdown }: { name: string; markdown: string }) =>
      api.updateHospitalInfo(name, markdown),
    onSuccess: (hospital) => queryClient.setQueryData(hospitalKeys.info, hospital),
  })
}

export function useUpdateDoctors() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (doctors: DoctorInput[]) => api.updateDoctors(doctors),
    onSuccess: (hospital) => queryClient.setQueryData(hospitalKeys.info, hospital),
  })
}

export function useHospitalInfo() {
  return useQuery({
    queryKey: hospitalKeys.info,
    queryFn: () => api.getHospitalInfo(),
    staleTime: 60_000,
  })
}

export function useAppointments(scope: AppointmentScope) {
  return useQuery({
    queryKey: appointmentKeys.list(scope),
    queryFn: () => api.listAppointments(scope),
    // Bookings arrive from live calls, so keep the list fresh while it's open.
    refetchInterval: 15_000,
  })
}

export function useUploadRecording() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => api.uploadRecording(file),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: callKeys.all }),
  })
}

export function useDeleteCall() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (callId: string) => api.deleteCall(callId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: callKeys.all }),
  })
}
