import { useEffect, useRef, useState } from 'react'
import { ApiError, streamAnalyzeCase, type RiskEvent, type SafetyReport } from '../api'
import { IconArrowLeft, IconArrowRight } from '../icons'
import { navigate } from '../router'
import { takePendingAnalysis } from '../pending'

interface ToolCard {
  kind: 'tool'
  tool: string
  args: Record<string, unknown>
  status: 'running' | 'ok' | 'rejected'
  elapsed_ms?: number
  summary?: string
  raw?: unknown
}

interface RiskCard extends RiskEvent {
  kind: 'risk'
}

type Card = ToolCard | RiskCard

const RISK_TEXT: Record<string, string> = {
  LOW_CONCERN: 'text-risk-low',
  CAUTION: 'text-risk-caution',
  HIGH_RISK: 'text-risk-high',
}

function Rail() {
  return <span aria-hidden className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-accent" />
}

function ToolCardView({ card }: { card: ToolCard }) {
  const isRunning = card.status === 'running'
  const isRejected = card.status === 'rejected'

  return (
    <div className="animate-card-in relative rounded-md border border-line bg-surface p-4 transition hover:border-line-strong">
      <Rail />
      <div className="flex items-center justify-between gap-3">
        <span className="font-mono text-sm text-ink">{card.tool}</span>
        <span
          className={`tabular font-mono text-xs ${
            isRunning ? 'text-ink-faint' : isRejected ? 'text-risk-caution' : 'text-risk-low'
          }`}
        >
          {isRunning ? 'running…' : `${card.elapsed_ms}ms`}
        </span>
      </div>
      <p className="mt-1.5 truncate font-mono text-xs text-ink-faint">
        {JSON.stringify(card.args)}
      </p>
      {card.summary && <p className="mt-2 text-sm text-ink-muted">{card.summary}</p>}
      {card.raw !== undefined && (
        <details className="mt-2 group">
          <summary className="cursor-pointer text-xs text-ink-faint transition hover:text-ink-muted">
            Raw JSON
          </summary>
          <pre className="mt-2 overflow-x-auto rounded bg-canvas p-2.5 font-mono text-xs text-ink-muted">
            {JSON.stringify(card.raw, null, 2)}
          </pre>
        </details>
      )}
    </div>
  )
}

function RiskCardView({ card }: { card: RiskCard }) {
  return (
    <div className="animate-card-in relative rounded-md border border-accent/40 bg-surface p-4">
      <Rail />
      <div className="flex items-center justify-between gap-3">
        <span className="font-display text-sm text-ink">Risk Engine</span>
        <span className={`font-mono text-xs font-medium ${RISK_TEXT[card.level] ?? 'text-ink-muted'}`}>
          {card.level}
        </span>
      </div>
      <p className="mt-1.5 font-mono text-xs text-ink-muted">score {card.score}</p>
      {card.rules_fired.length > 0 && (
        <p className="mt-2 text-xs text-ink-faint">{card.rules_fired.join(' · ')}</p>
      )}
    </div>
  )
}

export default function TracePage() {
  const [cards, setCards] = useState<Card[]>([])
  const [caseId, setCaseId] = useState<string | null>(null)
  const [report, setReport] = useState<SafetyReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const started = useRef(false)

  useEffect(() => {
    if (started.current) return
    started.current = true

    const pending = takePendingAnalysis()
    if (!pending) {
      setError('No analysis in progress.')
      return
    }

    ;(async () => {
      try {
        for await (const evt of streamAnalyzeCase(pending.text, pending.paymentContext)) {
          if (evt.event === 'ingest') {
            setCaseId(evt.data.case_id)
            window.history.replaceState({}, '', `/case/${evt.data.case_id}/trace`)
          } else if (evt.event === 'tool_start') {
            setCards((prev) => [
              ...prev,
              { kind: 'tool', tool: evt.data.tool, args: evt.data.args, status: 'running' },
            ])
          } else if (evt.event === 'tool_result') {
            setCards((prev) => {
              const next = [...prev]
              const idx = next.findLastIndex(
                (c): c is ToolCard => c.kind === 'tool' && c.tool === evt.data.tool && c.status === 'running',
              )
              if (idx !== -1) {
                next[idx] = {
                  ...(next[idx] as ToolCard),
                  status: evt.data.result_type,
                  elapsed_ms: evt.data.elapsed_ms,
                  summary: evt.data.summary,
                  raw: evt.data.raw,
                }
              }
              return next
            })
          } else if (evt.event === 'risk') {
            setCards((prev) => [...prev, { kind: 'risk', ...evt.data }])
          } else if (evt.event === 'report') {
            setReport(evt.data)
          }
        }
      } catch (err) {
        setError(err instanceof ApiError ? err.message : 'Lost connection to PayGuard mid-investigation.')
      }
    })()
  }, [])

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-6 py-12 sm:px-10">
      <button
        type="button"
        onClick={() => navigate('/')}
        className="flex items-center gap-1.5 self-start text-sm text-ink-faint transition hover:text-ink-muted"
      >
        <IconArrowLeft /> Check another message
      </button>

      <header>
        <h1 className="font-display text-xl font-semibold text-ink">
          Investigating
          {caseId && <span className="ml-2 font-mono text-base text-accent">{caseId}</span>}
        </h1>
        <p className="mt-1 text-sm text-ink-muted">
          Watch PayGuard decide what evidence it needs and go get it.
        </p>
      </header>

      {error && (
        <p className="rounded-md border border-risk-high/30 bg-risk-high/10 px-3 py-2 text-sm text-risk-high">
          {error}
        </p>
      )}

      <div className="flex flex-col gap-3 border-l border-line pl-6">
        {cards.map((card, i) =>
          card.kind === 'tool' ? <ToolCardView key={i} card={card} /> : <RiskCardView key={i} card={card} />,
        )}
        {cards.length === 0 && !error && (
          <p className="animate-card-in font-mono text-xs text-ink-faint">waiting for the first tool call&hellip;</p>
        )}
      </div>

      {report && (
        <button
          type="button"
          onClick={() => navigate(`/case/${report.case_id}`)}
          className="group flex items-center justify-center gap-2 rounded-md bg-accent px-5 py-3.5 font-display text-sm font-semibold text-accent-ink transition hover:bg-accent-strong active:scale-[0.99]"
        >
          View verdict
          <IconArrowRight className="transition group-hover:translate-x-0.5" />
        </button>
      )}
    </main>
  )
}
