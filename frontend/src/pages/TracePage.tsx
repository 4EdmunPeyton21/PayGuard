import { useEffect, useRef, useState } from 'react'
import { ApiError, streamAnalyzeCase, type RiskEvent, type SafetyReport } from '../api'
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

function ToolCardView({ card }: { card: ToolCard }) {
  const statusIcon = card.status === 'running' ? '⋯' : card.status === 'ok' ? '✓' : '✗'
  const statusColor =
    card.status === 'running' ? 'text-slate-400' : card.status === 'ok' ? 'text-emerald-600' : 'text-amber-600'

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between">
        <span className="font-mono text-sm font-medium text-slate-900">{card.tool}</span>
        <span className={`text-sm ${statusColor}`}>
          {statusIcon} {card.elapsed_ms !== undefined ? `${card.elapsed_ms}ms` : 'running...'}
        </span>
      </div>
      <p className="mt-1 text-xs text-slate-500">args: {JSON.stringify(card.args)}</p>
      {card.summary && <p className="mt-1 text-sm text-slate-700">{card.summary}</p>}
      {card.raw !== undefined && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs text-slate-400">Raw JSON</summary>
          <pre className="mt-1 overflow-x-auto rounded bg-slate-50 p-2 text-xs text-slate-600">
            {JSON.stringify(card.raw, null, 2)}
          </pre>
        </details>
      )}
    </div>
  )
}

function RiskCardView({ card }: { card: RiskCard }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between">
        <span className="font-medium text-slate-900">Risk Engine</span>
        <span className="text-sm text-slate-500">{card.level}</span>
      </div>
      <p className="mt-1 text-sm text-slate-700">score: {card.score}</p>
      {card.rules_fired.length > 0 && (
        <p className="mt-1 text-xs text-slate-500">rules fired: {card.rules_fired.join(', ')}</p>
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
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-4 px-4 py-12">
      <button type="button" onClick={() => navigate('/')} className="self-start text-sm font-medium text-slate-500 underline">
        &larr; Check another message
      </button>

      <header>
        <h1 className="text-xl font-semibold text-slate-900">Investigating{caseId ? ` ${caseId}` : '...'}</h1>
        <p className="text-sm text-slate-500">Watch PayGuard decide what evidence it needs and go get it.</p>
      </header>

      {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

      <div className="flex flex-col gap-3">
        {cards.map((card, i) =>
          card.kind === 'tool' ? <ToolCardView key={i} card={card} /> : <RiskCardView key={i} card={card} />,
        )}
      </div>

      {report && (
        <button
          type="button"
          onClick={() => navigate(`/case/${report.case_id}`)}
          className="rounded-lg bg-slate-900 px-4 py-3 font-medium text-white"
        >
          View verdict &rarr;
        </button>
      )}
    </main>
  )
}
