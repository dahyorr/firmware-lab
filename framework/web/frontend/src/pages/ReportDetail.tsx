import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getReport } from '../api'
import { exportReportPdf } from '../utils/exportPdf'

type AnyObj = Record<string, unknown>

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-6">
      <h2 className="text-xs text-gray-500 uppercase tracking-wider mb-3 pb-1 border-b border-gray-800">
        {title}
      </h2>
      {children}
    </div>
  )
}

function KV({ label, value }: { label: string; value: unknown }) {
  const display = value === null || value === undefined ? '—'
    : typeof value === 'boolean' ? (value ? 'yes' : 'no')
    : String(value)
  return (
    <div className="flex gap-4 py-0.5">
      <span className="text-gray-500 text-xs w-36 shrink-0">{label}</span>
      <span className="text-gray-200 text-xs font-mono">{display}</span>
    </div>
  )
}

const SEVERITY_COLOR: Record<string, string> = {
  CRITICAL: 'text-red-400',
  HIGH:     'text-orange-400',
  MEDIUM:   'text-yellow-400',
  LOW:      'text-blue-400',
  INFO:     'text-gray-400',
  high:     'text-orange-400',
  medium:   'text-yellow-400',
  low:      'text-blue-400',
  info:     'text-gray-400',
}

export default function ReportDetail() {
  const { filename } = useParams<{ filename: string }>()
  const [report, setReport] = useState<AnyObj | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!filename) return
    getReport(filename)
      .then(setReport)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false))
  }, [filename])

  if (loading) return <p className="text-gray-600 text-xs p-6 animate-pulse">Loading…</p>
  if (error) return <p className="text-red-400 text-xs p-6">{error}</p>
  if (!report) return null

  const fw    = report.firmware   as AnyObj ?? {}
  const em    = report.emulation  as AnyObj ?? {}
  const pr    = report.probe      as AnyObj ?? {}
  const cves  = (report.cve_matches   as AnyObj[]) ?? []
  const creds = (report.credentials   as AnyObj[]) ?? []
  const webs  = (report.web_findings  as AnyObj[]) ?? []
  const svcs  = (pr.services as AnyObj[]) ?? []
  const status = (report.status as string)
    ?? (em.success ? 'success' : em.image_id != null ? 'emulation_failed' : null)

  return (
    <div className="h-full overflow-y-auto scrollbar-thin">
      <div className="max-w-4xl mx-auto p-6">
        <div className="flex items-center justify-between gap-3 mb-6">
          <Link to="/reports" className="text-gray-500 hover:text-gray-300 text-xs">← Reports</Link>
          <button
            onClick={() => exportReportPdf(report)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            Export PDF
          </button>
        </div>

        <Section title="Firmware">
          <KV label="Name"       value={fw.name as string} />
          <KV label="SHA-256"    value={fw.sha256 as string} />
          <KV label="Size"       value={fw.size_bytes ? `${((fw.size_bytes as number) / 1e6).toFixed(2)} MB` : null} />
          <KV label="Run ID"     value={report.run_id as string} />
          <KV label="Timestamp"  value={report.timestamp as string} />
          <KV label="Status"     value={status} />
        </Section>

        <Section title="Emulation">
          <KV label="Image ID"      value={em.image_id as number} />
          <KV label="Architecture"  value={em.architecture as string} />
          <KV label="IP"            value={em.ip as string} />
          <KV label="From cache"    value={em.from_cache as boolean} />
          <KV label="Web service"   value={em.web_service as boolean} />
        </Section>

        {svcs.length > 0 && (
          <Section title={`Services (${svcs.length})`}>
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-500 border-b border-gray-800">
                  <th className="text-left py-1 pr-4 font-normal">Port</th>
                  <th className="text-left py-1 pr-4 font-normal">Protocol</th>
                  <th className="text-left py-1 pr-4 font-normal">Service</th>
                  <th className="text-left py-1 font-normal">Version</th>
                </tr>
              </thead>
              <tbody>
                {svcs.map((s, i) => (
                  <tr key={i} className="border-b border-gray-800/40">
                    <td className="py-1 pr-4 text-gray-300 font-mono">{s.port as number}</td>
                    <td className="py-1 pr-4 text-gray-500">{s.protocol as string}</td>
                    <td className="py-1 pr-4 text-gray-300">{s.service as string}</td>
                    <td className="py-1 text-gray-500">{(s.version as string) || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>
        )}

        {cves.length > 0 && (
          <Section title={`CVE Matches (${cves.length})`}>
            <div className="flex flex-col gap-3">
              {cves.map((c, i) => (
                <div key={i} className="bg-gray-900 border border-gray-800 rounded p-3">
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <span className="text-yellow-400 text-xs font-mono font-medium">{c.cve_id as string}</span>
                    <span className={`text-xs font-medium ${SEVERITY_COLOR[c.severity as string] ?? 'text-gray-400'}`}>
                      {c.severity as string} {c.cvss_score ? `(${c.cvss_score})` : ''}
                    </span>
                  </div>
                  <p className="text-gray-400 text-xs mb-1">{c.description as string}</p>
                  <p className="text-gray-600 text-xs">
                    port {c.port as number} · {c.service as string} {c.version as string}
                  </p>
                </div>
              ))}
            </div>
          </Section>
        )}

        {creds.filter((c) => c.success).length > 0 && (
          <Section title="Valid Credentials">
            {creds.filter((c) => c.success).map((c, i) => (
              <div key={i} className="text-xs text-red-400 font-mono py-0.5">
                {c.username as string}:{(c.password as string) || '(empty)'} — port {c.port as number} via {c.method as string}
              </div>
            ))}
          </Section>
        )}

        {webs.length > 0 && (
          <Section title={`Web Findings (${webs.length})`}>
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-500 border-b border-gray-800">
                  <th className="text-left py-1 pr-4 font-normal">Severity</th>
                  <th className="text-left py-1 pr-4 font-normal">Type</th>
                  <th className="text-left py-1 pr-4 font-normal">Path</th>
                  <th className="text-left py-1 font-normal">Detail</th>
                </tr>
              </thead>
              <tbody>
                {webs.map((w, i) => (
                  <tr key={i} className="border-b border-gray-800/40">
                    <td className={`py-1 pr-4 ${SEVERITY_COLOR[w.severity as string] ?? 'text-gray-400'}`}>
                      {w.severity as string}
                    </td>
                    <td className="py-1 pr-4 text-gray-300">{w.finding_type as string}</td>
                    <td className="py-1 pr-4 text-gray-400 font-mono">{w.path as string}</td>
                    <td className="py-1 text-gray-500">{w.detail as string}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>
        )}
      </div>
    </div>
  )
}
