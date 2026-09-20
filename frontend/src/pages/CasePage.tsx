import { useEffect, useState } from 'react'
import { ApiError, getCase, type Evidence, type RiskLevel, type SafetyReport } from '../api'
import { IconArrowLeft, IconOctagonStop, IconShieldCheck, IconTriangleAlert } from '../icons'
import { navigate } from '../router'

const LEVEL_STYLE: Record<
  RiskLevel,
  { Icon: typeof IconShieldCheck; label: string; text: string; border: string; glow: string }
> = {
  LOW_CONCERN: {
    Icon: IconShieldCheck,
    label: 'LOW CONCERN',
    text: 'text-risk-low',
    border: 'border-risk-low/30',
    glow: 'bg-risk-low/[0.08]',
  },
  CAUTION: {
    Icon: IconTriangleAlert,
    label: 'CAUTION',
    text: 'text-risk-caution',
    border: 'border-risk-caution/30',
    glow: 'bg-risk-caution/[0.08]',
  },
  HIGH_RISK: {
    Icon: IconOctagonStop,
    label: 'HIGH RISK',
    text: 'text-risk-high',
    border: 'border-risk-high/30',
    glow: 'bg-risk-high/[0.08]',
  },
}

function EvidenceChip({ evidence }: { evidence: Evidence }) {
  return (
    <span className="group relative inline-block">
      <span className="cursor-help rounded-sm border border-line-strong bg-surface-raised px-1.5 py-0.5 font-mono text-xs text-ink-muted transition group-hover:border-accent group-hover:text-accent">
        {evidence.id}
      </span>
      <span className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-2 w-64 -translate-x-1/2 rounded-md border border-line-strong bg-surface-raised/95 p-3 text-xs opacity-0 shadow-2xl backdrop-blur-sm transition group-hover:opacity-100">
        <span className="block text-ink">
          <span className="text-ink-faint">Observed &mdash; </span>
          {evidence.observed}
        </span>
        <span className="mt-1.5 block italic text-ink-muted">
          <span className="not-italic text-ink-faint">Interpretation &mdash; </span>
          {evidence.interpretation}
        </span>
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
      <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-4 px-6 py-12">
        <p className="rounded-md border border-risk-high/30 bg-risk-high/10 px-3 py-2 text-sm text-risk-high">
          {error}
        </p>
        <button
          type="button"
          onClick={() => navigate('/')}
          className="flex items-center gap-1.5 text-sm text-ink-muted transition hover:text-ink"
        >
          <IconArrowLeft /> Back to input
        </button>
      </main>
    )
  }

  if (!report) {
    return (
      <main className="mx-auto flex min-h-screen max-w-2xl items-center justify-center px-6">
        <p className="font-mono text-sm text-ink-faint">loading case&hellip;</p>
      </main>
    )
  }

  const level = LEVEL_STYLE[report.risk_level]
  const evidenceById = new Map(report.evidence.map((e) => [e.id, e]))

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-8 px-6 py-12 sm:px-10">
      <button
        type="button"
        onClick={() => navigate('/')}
        className="flex items-center gap-1.5 self-start text-sm text-ink-faint transition hover:text-ink-muted"
      >
        <IconArrowLeft /> Check another message
      </button>

      <div className={`relative overflow-hidden rounded-lg border ${level.border} bg-surface p-6`}>
        <div aria-hidden className={`pointer-events-none absolute -right-10 -top-10 h-48 w-48 rounded-full ${level.glow} blur-2xl`} />
        <div className="flex items-center gap-3">
          <level.Icon className={`h-7 w-7 ${level.text}`} />
          <span className={`font-display text-lg font-semibold tracking-wide ${level.text}`}>{level.label}</span>
          <span className="ml-auto font-mono text-xs text-ink-faint">{report.case_id}</span>
        </div>
        <h1 className="mt-4 max-w-[48ch] font-display text-2xl font-semibold leading-snug text-balance text-ink">
          {report.headline}
        </h1>
      </div>

      <section className="flex flex-col gap-3">
        <h2 className="font-mono text-xs tracking-[0.2em] text-ink-faint uppercase">Why</h2>
        {report.why.map((claim, i) => (
          <p key={i} className="flex flex-wrap items-center gap-2 rounded-md border border-line bg-surface p-4 text-ink">
            <span>{claim.text}</span>
            {claim.evidence_ids
              .map((id) => evidenceById.get(id))
              .filter((e): e is Evidence => Boolean(e))
              .map((e) => <EvidenceChip key={e.id} evidence={e} />)}
          </p>
        ))}
      </section>

      {report.recommended_actions.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="font-mono text-xs tracking-[0.2em] text-ink-faint uppercase">What you should do</h2>
          <ul className="flex flex-col gap-2">
            {report.recommended_actions.map((action, i) => (
              <li key={i}>
                <label className="flex cursor-pointer items-start gap-3 rounded-md border border-transparent p-1 transition hover:border-line">
                  <span
                    className={`relative mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-sm border transition ${
                      checked[i] ? 'border-accent' : 'border-line-strong'
                    }`}
                  >
                    <input
                      type="checkbox"
                      className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
                      checked={Boolean(checked[i])}
                      onChange={(e) => setChecked((prev) => ({ ...prev, [i]: e.target.checked }))}
                    />
                    {checked[i] && (
                      <svg viewBox="0 0 12 12" className="h-3 w-3 fill-none stroke-accent stroke-2">
                        <path d="M2 6.5 4.5 9 10 3" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    )}
                  </span>
                  <span className={checked[i] ? 'text-ink-faint line-through' : 'text-ink'}>{action}</span>
                </label>
              </li>
            ))}
          </ul>
        </section>
      )}

      {report.unverified.length > 0 && (
        <section className="flex flex-col gap-2 rounded-md border border-dashed border-line-strong bg-surface/60 p-4">
          <h2 className="font-mono text-xs tracking-[0.2em] text-ink-faint uppercase">
            Could not verify
          </h2>
          <ul className="flex flex-col gap-1">
            {report.unverified.map((item, i) => (
              <li key={i} className="text-sm text-ink-muted">
                {item}
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  )
}
