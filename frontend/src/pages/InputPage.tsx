import { useState } from 'react'
import { ApiError, ocrUpload } from '../api'
import { STEPS } from '../content'
import { IconShieldCheck, IconUpload } from '../icons'
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
    <main className="grid min-h-screen lg:grid-cols-[1.1fr_0.9fr]">
      {/* Left: the actual tool */}
      <div className="flex flex-col gap-8 px-6 py-12 sm:px-10 lg:px-16 lg:py-20">
        <button
          type="button"
          onClick={() => navigate('/')}
          className="flex w-fit items-center gap-2 text-ink-muted transition hover:text-ink"
        >
          <IconShieldCheck className="h-5 w-5 text-accent" />
          <span className="font-display text-sm tracking-[0.2em] uppercase">PayGuard</span>
        </button>

        <div className="max-w-md">
          <h1 className="font-display text-3xl leading-[1.15] text-balance text-ink sm:text-4xl">
            Don&rsquo;t trust it. Investigate it.
          </h1>
          <p className="mt-3 max-w-[36ch] text-ink-muted">
            Paste the message. PayGuard gathers evidence and shows you exactly why it made its
            call.
          </p>
        </div>

        <div className="flex flex-col gap-5">
          <label className="flex flex-col gap-2">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm font-medium text-ink-muted">Message to check</span>
              <label className="flex cursor-pointer items-center gap-1.5 text-sm font-medium text-accent transition hover:text-accent-strong">
                <IconUpload className="h-3.5 w-3.5" />
                {ocrLoading ? 'Reading screenshot…' : 'Upload a screenshot instead'}
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
              className="min-h-40 rounded-md border border-line bg-surface p-3.5 text-ink placeholder:text-ink-faint outline-none transition focus:border-accent"
              placeholder="Paste the SMS, WhatsApp message, or email here..."
              value={text}
              onChange={(e) => {
                setText(e.target.value)
                setOcrLowConfidence(false)
              }}
            />
            {ocrLowConfidence && (
              <p className="rounded-md border border-risk-caution/30 bg-risk-caution/10 px-3 py-2 text-sm text-risk-caution">
                PayGuard couldn&rsquo;t read that screenshot clearly &mdash; check the text above
                is correct before continuing.
              </p>
            )}
            {ocrError && (
              <p className="rounded-md border border-risk-high/30 bg-risk-high/10 px-3 py-2 text-sm text-risk-high">
                {ocrError}
              </p>
            )}
          </label>

          <label className="flex flex-col gap-2">
            <span className="text-sm font-medium text-ink-muted">
              What were you told this payment is for?{' '}
              <span className="text-ink-faint">(optional)</span>
            </span>
            <input
              className="rounded-md border border-line bg-surface p-3.5 text-ink placeholder:text-ink-faint outline-none transition focus:border-accent"
              placeholder="e.g. a refund, a delivery fee, a KYC update"
              value={paymentContext}
              onChange={(e) => setPaymentContext(e.target.value)}
            />
          </label>

          <button
            type="button"
            onClick={handleCheck}
            disabled={!text.trim()}
            className="group flex items-center justify-center gap-2 rounded-md bg-accent px-5 py-3.5 font-display text-sm font-semibold text-accent-ink transition hover:bg-accent-strong active:scale-[0.99] disabled:cursor-not-allowed disabled:bg-surface-raised disabled:text-ink-faint"
          >
            Investigate
          </button>
        </div>
      </div>

      {/* Right: ambient brand panel */}
      <div className="relative hidden overflow-hidden border-l border-line bg-surface lg:flex lg:flex-col lg:justify-center lg:px-16 lg:py-20">
        <div
          aria-hidden
          className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-accent/[0.07] blur-3xl"
        />
        <ol className="flex flex-col gap-10">
          {STEPS.map((step) => (
            <li key={step.n} className="flex gap-5">
              <span className="font-mono text-sm text-accent">{step.n}</span>
              <div className="flex flex-col gap-1">
                <span className="font-display text-base text-ink">{step.label}</span>
                <p className="max-w-[32ch] text-sm text-ink-muted">{step.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </main>
  )
}
