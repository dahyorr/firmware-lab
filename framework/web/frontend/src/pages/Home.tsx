import { useCallback, useEffect, useState } from 'react'
import { listFirmware } from '../api'
import type { FirmwareImage, Vendor } from '../api'
import FirmwareBrowser from '../components/FirmwareBrowser'
import RunPanel from '../components/RunPanel'
import UploadZone from '../components/UploadZone'

export default function Home() {
  const [vendors, setVendors] = useState<Vendor[]>([])
  const [selected, setSelected] = useState<FirmwareImage | null>(null)
  const [showUpload, setShowUpload] = useState(false)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const data = await listFirmware()
      setVendors(data.vendors)
    } catch {
      // leave empty
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  return (
    <div className="flex h-full">
      {/* Left: firmware browser */}
      <div className="w-72 shrink-0 border-r border-gray-800 flex flex-col h-full">
        {loading ? (
          <p className="text-gray-600 text-xs px-4 pt-4 animate-pulse">Loading…</p>
        ) : (
          <FirmwareBrowser
            vendors={vendors}
            selected={selected}
            onSelect={setSelected}
            onUpload={() => setShowUpload(true)}
          />
        )}
      </div>

      {/* Right: run configuration */}
      <div className="flex-1 flex flex-col h-full">
        <RunPanel selected={selected} />
      </div>

      {showUpload && (
        <UploadZone
          onClose={() => setShowUpload(false)}
          onUploaded={() => { load(); setShowUpload(false) }}
        />
      )}
    </div>
  )
}
