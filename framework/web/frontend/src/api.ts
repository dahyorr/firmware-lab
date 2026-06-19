const BASE = '/api'

export interface FirmwareImage {
  name: string
  path: string
  size: number
  brand: string
  has_report: boolean
}

export interface Vendor {
  name: string
  images: FirmwareImage[]
}

export interface RunState {
  run_id: string
  firmware_name: string
  firmware_path: string
  brand: string
  profile: string
  status: string
  queued_at: string
  started_at: string | null
  completed_at: string | null
  report_path: string | null
  services: number
  cves: number
  cred_hits: number
  web_findings: number
  error: string | null
}

export interface ReportSummary {
  filename: string
  firmware: string
  timestamp: string
  status: string
  run_id: string
  architecture: string | null
  ip: string | null
  from_cache: boolean
  services: number
  cves: number
  web_findings: number
}

export async function listFirmware(): Promise<{ vendors: Vendor[] }> {
  const r = await fetch(`${BASE}/firmware`)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function uploadFirmware(vendor: string, file: File): Promise<FirmwareImage> {
  const form = new FormData()
  form.append('vendor', vendor)
  form.append('file', file)
  const r = await fetch(`${BASE}/firmware/upload`, { method: 'POST', body: form })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function submitRun(
  firmware_path: string,
  brand: string,
  profile: string,
): Promise<{ run_id: string }> {
  const r = await fetch(`${BASE}/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ firmware_path, brand, profile }),
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function listRuns(): Promise<{ runs: RunState[] }> {
  const r = await fetch(`${BASE}/runs`)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function listReports(): Promise<{ reports: ReportSummary[] }> {
  const r = await fetch(`${BASE}/reports`)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function getReport(filename: string): Promise<Record<string, unknown>> {
  const r = await fetch(`${BASE}/reports/${encodeURIComponent(filename)}`)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export function openRunWS(run_id: string): WebSocket {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return new WebSocket(`${proto}://${window.location.host}/api/runs/${run_id}/ws`)
}
