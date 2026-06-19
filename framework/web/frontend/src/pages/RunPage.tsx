import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { openRunWS } from '../api'
import type { RunState } from '../api'

interface LogEvent {
  type: string
  module?: string
  msg?: string
  detail?: string
  error?: string
  data?: Record<string, unknown>
  status?: string
  state?: RunState
}

const MODULE_LABELS: Record<string, string> = {
  acquisition:        'Acquisition',
  emulation:          'Emulation',
  orchestrator:       'Orchestrator',
  probe:              'Port Scan',
  cve_matcher:        'CVE Matching',
  credential_tester:  'Credential Test',
  web_prober:         'Web Probe',
}

const STATUS_COLOR: Record<string, string> = {
  queued:            'text-gray-400',
  running:           'text-yellow-400',
  success:           'text-green-400',
  emulation_failed:  'text-orange-400',
  failed:            'text-red-400',
}

export default function RunPage() {
  const { runId } = useParams<{ runId: string }>()
  const [logs, setLogs] = useState<LogEvent[]>([])
  const [state, setState] = useState<RunState | null>(null)
  const [done, setDone] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!runId) return
    const ws = openRunWS(runId)

    ws.onmessage = (e) => {
      const ev: LogEvent = JSON.parse(e.data)
      if (ev.type === 'status' && ev.state) {
        setState(ev.state)
      } else if (ev.type === 'done') {
        setDone(true)
        ws.close()
      } else {
        setLogs((prev) => [...prev, ev])
      }
    }

    ws.onerror = () => setDone(true)

    return () => ws.close()
  }, [runId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  const renderEvent = (ev: LogEvent, i: number) => {
    if (ev.type === 'log') {
      const line = ev.msg ?? ''
      const color = line.startsWith('[!]') ? 'text-yellow-400'
        : line.startsWith('[-]') ? 'text-red-400'
        : line.startsWith('[+]') ? 'text-green-400'
        : 'text-gray-400'
      return (
        <div key={i} className={`text-xs font-mono ${color}`}>{line}</div>
      )
    }
    if (ev.type === 'start') {
      return (
        <div key={i} className="text-xs flex gap-2 text-gray-500">
          <span className="text-blue-500">▶</span>
          <span>{MODULE_LABELS[ev.module ?? ''] ?? ev.module}</span>
          {ev.detail && <span className="text-gray-600">{ev.detail}</span>}
        </div>
      )
    }
    if (ev.type === 'progress') {
      return (
        <div key={i} className="text-xs text-gray-500 pl-4">
          ↳ {ev.msg}
        </div>
      )
    }
    if (ev.type === 'success') {
      const mod = MODULE_LABELS[ev.module ?? ''] ?? ev.module
      return (
        <div key={i} className="text-xs text-green-500 flex gap-2">
          <span>✓</span>
          <span>{mod}</span>
          {ev.data && Object.keys(ev.data).length > 0 && (
            <span className="text-gray-500">{JSON.stringify(ev.data)}</span>
          )}
        </div>
      )
    }
    if (ev.type === 'failure') {
      return (
        <div key={i} className="text-xs text-red-400 flex gap-2">
          <span>✗</span>
          <span>{MODULE_LABELS[ev.module ?? ''] ?? ev.module}</span>
          <span className="text-red-600">{ev.error}</span>
        </div>
      )
    }
    return null
  }

  const status = state?.status ?? 'running'
  const statusCls = STATUS_COLOR[status] ?? 'text-gray-400'

  return (
    <div className="flex flex-col h-full p-6 gap-4 max-w-4xl mx-auto w-full">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <Link to="/" className="text-gray-500 hover:text-gray-300 text-xs">← Back</Link>
            <span className="text-gray-700 text-xs">run</span>
            <span className="text-gray-400 text-xs font-mono">{runId}</span>
          </div>
          <h1 className="text-sm text-gray-200 font-medium truncate">
            {state?.firmware_name ?? '…'}
          </h1>
          <div className="flex gap-3 mt-1 text-xs text-gray-500">
            {state?.brand && <span>brand: {state.brand}</span>}
            {state?.profile && <span>profile: {state.profile}</span>}
          </div>
        </div>
        <div className="text-right">
          <span className={`text-sm font-medium ${statusCls}`}>
            {!done && status === 'running' && (
              <span className="inline-block animate-pulse mr-1">●</span>
            )}
            {status}
          </span>
          {state?.started_at && (
            <p className="text-xs text-gray-600 mt-1">
              {new Date(state.started_at).toLocaleTimeString()}
            </p>
          )}
        </div>
      </div>

      {/* Log stream */}
      <div className="flex-1 bg-gray-900 border border-gray-800 rounded-lg p-4 overflow-y-auto scrollbar-thin flex flex-col gap-0.5">
        {logs.length === 0 && !done && (
          <p className="text-gray-600 text-xs animate-pulse">Waiting for run to start…</p>
        )}
        {logs.map(renderEvent)}
        <div ref={bottomRef} />
      </div>

      {/* Summary when done */}
      {done && state && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            ['Services', state.services],
            ['CVEs', state.cves],
            ['Cred hits', state.cred_hits],
            ['Web findings', state.web_findings],
          ].map(([label, val]) => (
            <div key={label as string}>
              <p className="text-xs text-gray-500">{label}</p>
              <p className={`text-2xl font-mono ${Number(val) > 0 ? 'text-yellow-400' : 'text-gray-400'}`}>
                {val}
              </p>
            </div>
          ))}
        </div>
      )}

      {done && state?.report_path && (
        <div className="flex justify-end">
          <Link
            to={`/reports/${encodeURIComponent(
              state.report_path.split('/').pop() ?? '',
            )}`}
            className="text-xs text-green-400 hover:text-green-300 border border-green-800 px-3 py-1.5 rounded transition-colors"
          >
            View Report →
          </Link>
        </div>
      )}
    </div>
  )
}
