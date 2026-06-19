import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { submitRun } from '../api'
import type { FirmwareImage } from '../api'

interface Props {
  selected: FirmwareImage | null
}

const PROFILES = ['fast', 'comprehensive', 'stealth'] as const

export default function RunPanel({ selected }: Props) {
  const nav = useNavigate()
  const [brand, setBrand] = useState('')
  const [profile, setProfile] = useState<string>('fast')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  // When firmware changes, reset brand to the derived value
  const effectiveBrand = brand || selected?.brand || ''

  const submit = async () => {
    if (!selected) return
    setSubmitting(true)
    setError('')
    try {
      const { run_id } = await submitRun(selected.path, effectiveBrand, profile)
      nav(`/run/${run_id}`)
    } catch (e) {
      setError(String(e))
      setSubmitting(false)
    }
  }

  if (!selected) {
    return (
      <div className="flex flex-col h-full items-center justify-center text-gray-600 text-sm gap-2">
        <span className="text-3xl">⬅</span>
        <p>Select a firmware image to begin</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full p-6 gap-5">
      <div>
        <p className="text-xs text-gray-500 uppercase tracking-wider mb-3">Selected Firmware</p>
        <p className="text-sm text-green-400 font-medium truncate">{selected.name}</p>
        <p className="text-xs text-gray-600 truncate mt-0.5">{selected.path}</p>
      </div>

      <div>
        <label className="block text-xs text-gray-500 mb-1">Brand</label>
        <input
          value={effectiveBrand}
          onChange={(e) => setBrand(e.target.value)}
          placeholder="auto-derived"
          className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-green-600"
        />
        <p className="text-xs text-gray-600 mt-1">Passed to FirmAE run.sh -c &lt;brand&gt;</p>
      </div>

      <div>
        <label className="block text-xs text-gray-500 mb-1">Profile</label>
        <div className="flex gap-2">
          {PROFILES.map((p) => (
            <button
              key={p}
              onClick={() => setProfile(p)}
              className={`flex-1 py-1.5 rounded text-xs transition-colors ${
                profile === p
                  ? 'bg-green-700 text-white'
                  : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
              }`}
            >
              {p}
            </button>
          ))}
        </div>
        <p className="text-xs text-gray-600 mt-1">
          {profile === 'fast' && 'Top 100 ports, quick triage'}
          {profile === 'comprehensive' && 'All 65535 ports, full version detection'}
          {profile === 'stealth' && 'SYN scan, slow timing'}
        </p>
      </div>

      {error && <p className="text-red-400 text-xs">{error}</p>}

      <button
        onClick={submit}
        disabled={submitting}
        className="mt-auto w-full py-3 rounded font-medium text-sm transition-colors disabled:opacity-50 bg-green-700 hover:bg-green-600 text-white"
      >
        {submitting ? 'Submitting…' : '▶  Run Analysis'}
      </button>
    </div>
  )
}
