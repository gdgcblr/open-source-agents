/**
 * RepoLens — TypeScript API Client
 * Typed wrappers for all backend endpoints.
 * All API calls go through /api (proxied to FastAPI in dev, same-origin in prod).
 */

const BASE = '/api'

export interface ScannerStatus {
  available: boolean
  exit_code: number | null
  error_message: string | null
  finding_count: number
}

export interface Finding {
  finding_id: string
  title: string
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO' | 'UNKNOWN'
  category: string
  scanner: string
  rule_id: string | null
  advisory_ref: string | null
  file_path: string | null
  line_start: number | null
  line_end: number | null
  evidence: string | null
  remediation: string | null
  source_url: string | null
  provenance: 'scanner' | 'ai_suggestion'
}

export interface AuditReport {
  repository_url: string
  repository_name: string
  commit_sha: string | null
  tech_stack: string[]
  findings: Finding[]
  scanner_status: Record<string, ScannerStatus>
  ai_summary: string | null
  ai_prioritized_actions: string[]
  ai_available: boolean
  is_demo: boolean
  scan_duration_seconds: number | null
  generated_at: string
}

export interface AuditSummary {
  id: number
  repository_url: string
  repository_name: string
  scan_status: string
  is_demo: boolean
  commit_sha: string | null
  created_at: string
  updated_at: string
  critical_count: number
  high_count: number
  medium_count: number
  low_count: number
  total_findings: number
}

export interface AuditDetail extends AuditSummary {
  report_json: AuditReport | null
  report_markdown: string | null
}

export interface HealthResponse {
  status: string
  version: string
  database: string
  gemini_configured: boolean
}

export interface ScanRequest {
  repository_url: string
}

export interface ScanResponse {
  audit_id: number
  status: string
  message: string
}

async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, options)
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`API error ${res.status}: ${body}`)
  }
  return res.json() as Promise<T>
}

export async function getHealth(): Promise<HealthResponse> {
  return fetchJSON<HealthResponse>(`${BASE}/health`)
}

export async function getAudits(): Promise<AuditSummary[]> {
  return fetchJSON<AuditSummary[]>(`${BASE}/audits`)
}

export async function getAudit(id: number): Promise<AuditDetail> {
  return fetchJSON<AuditDetail>(`${BASE}/audits/${id}`)
}

export async function startScan(url: string): Promise<ScanResponse> {
  return fetchJSON<ScanResponse>(`${BASE}/scans`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ repository_url: url }),
  })
}

export function getReportDownloadUrl(id: number, format: 'json' | 'markdown'): string {
  return `${BASE}/audits/${id}/report?format=${format}`
}
