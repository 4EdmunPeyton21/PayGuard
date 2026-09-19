import { useEffect, useState } from 'react'
import { ApiError, getCase, type Evidence, type RiskLevel, type SafetyReport } from '../api'
import { navigate } from '../router'

const LEVEL_STYLE: Record<RiskLevel, { icon: string; label: string; classes: string }> = {
  LOW_CONCERN: { icon: '✓', label: 'LOW CONCERN', classes: 'bg-emerald-50 text-emerald-800 border-emerald-300' },
  CAUTION: { icon: '⚠', label: 'CAUTION', classes: 'bg-amber-50 text-amber-800 border-amber-300' },
  HIGH_RISK: { icon: '⛔', label: 'HIGH RISK', classes: 'bg-red-50 text-red-800 border-red-300' },
}

function EvidenceChip({ evidence }: { evidence: Evidence }) {
  return (
    <span className="group relative inline-block">
      <span className="cursor-help rounded-full border border-slate-300 bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">
        {evidence.id}
      </span>
      <span className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-2 w-64 -translate-x-1/2 rounded-lg border border-slate-200 bg-white p-3 text-xs opacity-0 shadow-lg transition group-hover:opacity-100">
        <span className="block font-medium text-slate-900">Observed: {evidence.observed}</span>
        <span className="mt-1 block italic text-slate-500">Interpretation: {evidence.interpretation}</span>
      </span>
    </span>
  )
}

export default function CasePage({ caseId }: { caseId: string }) {
  const [report, setReport] = useState<SafetyReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [checked, setChecked] = useState<Record<number, boolean>>({})

  useEffect(() => {
    getCase(caseId)
      .then(setReport)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load this case.'))
  }, [caseId])

  if (error) {
    return (
      <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-4 px-4 py-12">
        <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
        <button type="button" onClick={() => navigate('/')} className="text-sm font-medium text-slate-600 underline">
          Back to input
        </button>
      </main>
    )
  }

  if (!report) {
    return (
      <main className="mx-auto flex min-h-screen max-w-2xl items-center justify-center px-4">
        <p className="text-slate-500">Loading case...</p>
      </main>
    )
  }

  const level = LEVEL_STYLE[report.risk_level]
  const evidenceById = new Map(report.evidence.map((e) => [e.id, e]))

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-4 py-12">
      <button type="button" onClick={() => navigate('/')} className="self-start text-sm font-medium text-slate-500 underline">
        &larr; Check another message
      </button>

      <div className={`flex items-center gap-3 rounded-lg border px-4 py-3 ${level.classes}`}>
        <span aria-hidden className="text-2xl leading-none">{level.icon}</span>
        <span className="font-semibold tracking-wide">{level.label}</span>
      </div>

      <h1 className="text-xl font-semibold text-slate-900">{report.headline}</h1>

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Why</h2>
        {report.why.map((claim, i) => (
          <p key={i} className="flex flex-wrap items-center gap-2 rounded-lg bg-slate-50 p-3 text-slate-800">
            <span>{claim.text}</span>
            {claim.evidence_ids
              .map((id) => evidenceById.get(id))
              .filter((e): e is Evidence => Boolean(e))
              .map((e) => <EvidenceChip key={e.id} evidence={e} />)}
          </p>
        ))}
      </section>

      {report.recommended_actions.length > 0 && (
        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">What you should do</h2>
          <ul className="flex flex-col gap-2">
            {report.recommended_actions.map((action, i) => (
              <li key={i}>
                <label className="flex items-start gap-2 text-slate-800">
                  <input
                    type="checkbox"
                    className="mt-1"
                    checked={Boolean(checked[i])}
                    onChange={(e) => setChecked((prev) => ({ ...prev, [i]: e.target.checked }))}
                  />
                  <span className={checked[i] ? 'line-through text-slate-400' : ''}>{action}</span>
                </label>
              </li>
            ))}
          </ul>
        </section>
      )}

      {report.unverified.length > 0 && (
        <section className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-slate-50 p-4">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
            Things PayGuard could not verify
          </h2>
          <ul className="list-inside list-disc text-slate-600">
            {report.unverified.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </section>
      )}
    </main>
  )
}
