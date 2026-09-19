import { useState } from 'react'
import { ApiError, ocrUpload } from '../api'
import { navigate } from '../router'
import { setPendingAnalysis } from '../pending'

export default function InputPage() {
  const [text, setText] = useState('')
  const [paymentContext, setPaymentContext] = useState('')
  const [ocrLoading, setOcrLoading] = useState(false)
  const [ocrLowConfidence, setOcrLowConfidence] = useState(false)
  const [ocrError, setOcrError] = useState<string | null>(null)

  function handleCheck() {
    if (!text.trim()) return
    setPendingAnalysis({ text, paymentContext })
    navigate('/analyzing')
  }

  async function handleUpload(file: File) {
    setOcrLoading(true)
    setOcrError(null)
    setOcrLowConfidence(false)
    try {
      const result = await ocrUpload(file)
      setText(result.text)
      setOcrLowConfidence(result.low_confidence)
    } catch (err) {
      setOcrError(err instanceof ApiError ? err.message : 'Could not read that screenshot.')
    } finally {
      setOcrLoading(false)
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-4 py-12">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">PayGuard</h1>
        <p className="mt-1 text-slate-600">
          Paste a suspicious message below. PayGuard investigates it and shows you the evidence.
        </p>
      </header>

      <label className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-slate-700">Message to check</span>
          <label className="cursor-pointer text-sm font-medium text-slate-500 underline">
            {ocrLoading ? 'Reading screenshot...' : 'Upload a screenshot instead'}
            <input
              type="file"
              accept="image/*"
              className="hidden"
              disabled={ocrLoading}
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) void handleUpload(file)
                e.target.value = ''
              }}
            />
          </label>
        </div>
        <textarea
          className="min-h-40 rounded-lg border border-slate-300 p-3 text-slate-900 outline-none focus:border-slate-500"
          placeholder="Paste the SMS, WhatsApp message, or email here..."
          value={text}
          onChange={(e) => {
            setText(e.target.value)
            setOcrLowConfidence(false)
          }}
        />
        {ocrLowConfidence && (
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
            PayGuard couldn't read that screenshot clearly — please check the text above is
            correct before continuing.
          </p>
        )}
        {ocrError && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{ocrError}</p>}
      </label>

      <label className="flex flex-col gap-2">
        <span className="text-sm font-medium text-slate-700">
          What were you told this payment is for? <span className="text-slate-400">(optional)</span>
        </span>
        <input
          className="rounded-lg border border-slate-300 p-3 text-slate-900 outline-none focus:border-slate-500"
          placeholder="e.g. a refund, a delivery fee, a KYC update"
          value={paymentContext}
          onChange={(e) => setPaymentContext(e.target.value)}
        />
      </label>

      <button
        type="button"
        onClick={handleCheck}
        disabled={!text.trim()}
        className="rounded-lg bg-slate-900 px-4 py-3 font-medium text-white transition disabled:cursor-not-allowed disabled:opacity-40"
      >
        Check
      </button>
    </main>
  )
}
