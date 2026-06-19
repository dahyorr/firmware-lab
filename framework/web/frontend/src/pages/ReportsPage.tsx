import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listReports } from '../api'
import type { ReportSummary } from '../api'

const STATUS_BADGE: Record<string, string> = {
  success:           'bg-green-900/60 text-green-400',
  emulation_failed:  'bg-orange-900/60 text-orange-400',
  failed:            'bg-red-900/60 text-red-400',
}

export default function ReportsPage() {
  const [reports, setReports] = useState<ReportSummary[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    listReports()
      .then((d) => setReports(d.reports))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="h-full overflow-y-auto scrollbar-thin">
      <div className="max-w-5xl mx-auto p-6">
        <h1 className="text-sm text-gray-400 uppercase tracking-wider mb-4">Reports</h1>
        {loading && <p className="text-gray-600 text-xs animate-pulse">Loading…</p>}
        {!loading && reports.length === 0 && (
          <p className="text-gray-600 text-sm">No reports yet. Run an analysis first.</p>
        )}
        {reports.length > 0 && (
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="text-gray-500 border-b border-gray-800">
                <th className="text-left py-2 pr-4 font-normal">Firmware</th>
                <th className="text-left py-2 pr-4 font-normal">Status</th>
                <th className="text-left py-2 pr-4 font-normal">Arch / IP</th>
                <th className="text-right py-2 pr-4 font-normal">Svcs</th>
                <th className="text-right py-2 pr-4 font-normal">CVEs</th>
                <th className="text-right py-2 pr-4 font-normal">Web</th>
                <th className="text-right py-2 font-normal">Date</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {reports.map((r) => (
                <tr key={r.filename} className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors">
                  <td className="py-2 pr-4 max-w-xs">
                    <span className="text-gray-200 truncate block">{r.firmware}</span>
                    <span className="text-gray-600">{r.run_id}</span>
                  </td>
                  <td className="py-2 pr-4">
                    <span className={`px-2 py-0.5 rounded text-xs ${STATUS_BADGE[r.status] ?? 'bg-gray-800 text-gray-400'}`}>
                      {r.status}
                    </span>
                  </td>
                  <td className="py-2 pr-4 text-gray-400">
                    {r.architecture && <span>{r.architecture}</span>}
                    {r.ip && <span className="ml-2 text-gray-500">{r.ip}</span>}
                  </td>
                  <td className="py-2 pr-4 text-right text-gray-400">{r.services || '—'}</td>
                  <td className={`py-2 pr-4 text-right ${r.cves > 0 ? 'text-yellow-400' : 'text-gray-600'}`}>
                    {r.cves || '—'}
                  </td>
                  <td className={`py-2 pr-4 text-right ${r.web_findings > 0 ? 'text-yellow-400' : 'text-gray-600'}`}>
                    {r.web_findings || '—'}
                  </td>
                  <td className="py-2 pr-4 text-right text-gray-600 whitespace-nowrap">
                    {r.timestamp ? new Date(r.timestamp).toLocaleDateString() : ''}
                  </td>
                  <td className="py-2 text-right">
                    <Link
                      to={`/reports/${encodeURIComponent(r.filename)}`}
                      className="text-green-500 hover:text-green-400 transition-colors"
                    >
                      View →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
