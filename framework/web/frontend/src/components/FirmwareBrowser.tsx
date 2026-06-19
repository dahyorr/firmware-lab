import { useState } from 'react'
import type { FirmwareImage, Vendor } from '../api'

interface Props {
  vendors: Vendor[]
  selected: FirmwareImage | null
  onSelect: (img: FirmwareImage) => void
  onUpload: () => void
}

export default function FirmwareBrowser({ vendors, selected, onSelect, onUpload }: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(
    () => new Set(vendors.map((v) => v.name)),
  )

  const toggle = (name: string) =>
    setExpanded((prev) => {
      const next = new Set(prev)
      next.has(name) ? next.delete(name) : next.add(name)
      return next
    })

  const fmt = (bytes: number) => {
    if (bytes > 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`
    return `${(bytes / 1_000).toFixed(0)} KB`
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-800">
        <span className="text-xs text-gray-500 uppercase tracking-wider">Firmware Library</span>
        <button
          onClick={onUpload}
          className="text-xs text-green-400 hover:text-green-300 border border-green-800 px-2 py-0.5 rounded transition-colors"
        >
          ↑ Upload
        </button>
      </div>
      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {vendors.length === 0 && (
          <p className="text-gray-600 text-xs px-4 pt-4">
            No firmware found in ~/project/firmware/
          </p>
        )}
        {vendors.map((v) => (
          <div key={v.name}>
            <button
              onClick={() => toggle(v.name)}
              className="w-full flex items-center gap-2 px-4 py-2 text-left hover:bg-gray-800 transition-colors"
            >
              <span className="text-gray-500 text-xs">{expanded.has(v.name) ? '▾' : '▸'}</span>
              <span className="text-gray-300 text-xs font-medium">{v.name}</span>
              <span className="text-gray-600 text-xs ml-auto">{v.images.length}</span>
            </button>
            {expanded.has(v.name) &&
              v.images.map((img) => (
                <button
                  key={img.path}
                  onClick={() => onSelect(img)}
                  className={`w-full flex items-start gap-2 pl-8 pr-4 py-1.5 text-left transition-colors ${
                    selected?.path === img.path
                      ? 'bg-green-900/40 border-l-2 border-green-500'
                      : 'hover:bg-gray-800/60 border-l-2 border-transparent'
                  }`}
                >
                  <span className="flex-1 min-w-0">
                    <span className="block text-xs text-gray-200 truncate">{img.name}</span>
                    <span className="text-xs text-gray-600">{fmt(img.size)}</span>
                  </span>
                  {img.has_report && (
                    <span className="text-green-600 text-xs mt-0.5 shrink-0" title="Has report">
                      ✓
                    </span>
                  )}
                </button>
              ))}
          </div>
        ))}
      </div>
    </div>
  )
}
