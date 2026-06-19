import { useRef, useState, DragEvent } from 'react'
import { uploadFirmware } from '../api'

interface Props {
  onClose: () => void
  onUploaded: () => void
}

export default function UploadZone({ onClose, onUploaded }: Props) {
  const [vendor, setVendor] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const EXTS = ['.zip', '.bin', '.img', '.trx', '.chk']

  const pick = (f: File) => {
    if (!EXTS.some((e) => f.name.toLowerCase().endsWith(e))) {
      setError(`Unsupported type. Allowed: ${EXTS.join(', ')}`)
      return
    }
    setFile(f)
    setError('')
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files[0]
    if (f) pick(f)
  }

  const submit = async () => {
    if (!file || !vendor.trim()) return
    setUploading(true)
    setError('')
    try {
      await uploadFirmware(vendor.trim(), file)
      onUploaded()
      onClose()
    } catch (e) {
      setError(String(e))
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-gray-900 border border-gray-700 rounded-lg p-6 w-full max-w-md"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium text-gray-200">Upload Firmware</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 text-lg leading-none">×</button>
        </div>

        <div className="mb-4">
          <label className="block text-xs text-gray-500 mb-1">Vendor / folder name</label>
          <input
            value={vendor}
            onChange={(e) => setVendor(e.target.value)}
            placeholder="e.g. dlink"
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-green-600"
          />
        </div>

        <div
          className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors mb-4 ${
            dragging ? 'border-green-500 bg-green-900/20' : 'border-gray-700 hover:border-gray-500'
          }`}
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
        >
          <input
            ref={inputRef}
            type="file"
            className="hidden"
            accept={EXTS.join(',')}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) pick(f) }}
          />
          {file ? (
            <div>
              <p className="text-green-400 text-sm">{file.name}</p>
              <p className="text-gray-500 text-xs mt-1">{(file.size / 1_000_000).toFixed(1)} MB</p>
            </div>
          ) : (
            <div>
              <p className="text-gray-400 text-sm">Drop firmware here</p>
              <p className="text-gray-600 text-xs mt-1">{EXTS.join('  ')}</p>
            </div>
          )}
        </div>

        {error && <p className="text-red-400 text-xs mb-3">{error}</p>}

        <button
          onClick={submit}
          disabled={!file || !vendor.trim() || uploading}
          className="w-full py-2 rounded text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed bg-green-700 hover:bg-green-600 text-white"
        >
          {uploading ? 'Uploading…' : 'Upload'}
        </button>
      </div>
    </div>
  )
}
