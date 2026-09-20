import { STEPS } from '../content'
import { IconArrowRight, IconOctagonStop, IconShieldCheck, IconTriangleAlert } from '../icons'
import { navigate } from '../router'

const CREDIBILITY = [
  { Icon: IconShieldCheck, label: 'Every claim cited', body: 'No verdict without a quoted piece of evidence behind it.' },
  { Icon: IconTriangleAlert, label: 'Evidence over guesses', body: 'An agent investigates first — links, senders, payment patterns — then decides.' },
  { Icon: IconOctagonStop, label: 'Deterministic risk engine', body: 'Scoring runs on a fixed, auditable policy — not a black-box model call.' },
]

export default function LandingPage() {
  return (
    <main className="bg-canvas">
      {/* Hero */}
      <section className="relative overflow-hidden border-b border-line px-6 py-20 sm:px-10 sm:py-28 lg:px-16">
        <div
          aria-hidden
          className="pointer-events-none absolute -right-32 -top-32 h-[28rem] w-[28rem] rounded-full bg-accent/[0.08] blur-3xl"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -bottom-40 left-1/3 h-96 w-96 rounded-full bg-risk-low/[0.05] blur-3xl"
        />

        <nav className="relative mb-16 flex items-center justify-between sm:mb-24">
          <div className="flex items-center gap-2 text-ink-muted">
            <IconShieldCheck className="h-5 w-5 text-accent" />
            <span className="font-display text-sm font-semibold tracking-[0.2em] uppercase text-ink">PayGuard</span>
          </div>
          <button
            type="button"
            onClick={() => navigate('/check')}
            className="rounded-md border border-line-strong px-4 py-2 text-sm font-medium text-ink-muted transition hover:border-accent hover:text-ink"
          >
            Open the tool
          </button>
        </nav>

        <div className="relative grid gap-16 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
          <div>
            <h1 className="font-display text-5xl font-bold leading-[1.08] text-balance text-ink sm:text-6xl lg:text-6xl xl:text-7xl">
              Don&rsquo;t trust it. <span className="text-accent">Investigate it.</span>
            </h1>
            <p className="mt-6 max-w-[42ch] text-lg text-ink-muted">
              PayGuard reads the suspicious message, investigates it like an analyst would, and
              shows you the evidence behind the verdict &mdash; not just a score.
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-4">
              <button
                type="button"
                onClick={() => navigate('/check')}
                className="group flex items-center gap-2 rounded-md bg-accent px-6 py-3.5 font-display text-sm font-semibold text-accent-ink transition hover:bg-accent-strong active:scale-[0.99]"
              >
                Investigate a message
                <IconArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
              </button>
              <a
                href="#how-it-works"
                className="rounded-md px-6 py-3.5 text-sm font-medium text-ink-muted transition hover:text-ink"
              >
                See how it works
              </a>
            </div>
          </div>

          {/* Ambient evidence-card visual, no external assets */}
          <div className="relative hidden lg:block">
            <div className="animate-card-in rounded-lg border border-line-strong bg-surface p-6 shadow-2xl">
              <div className="flex items-center gap-2 border-b border-line pb-4">
                <IconTriangleAlert className="h-5 w-5 text-risk-caution" />
                <span className="font-display text-sm text-risk-caution">CAUTION</span>
              </div>
              <div className="mt-4 flex flex-col gap-3">
                <div className="flex items-start gap-2">
                  <span className="mt-0.5 rounded-sm border border-line-strong bg-surface-raised px-1.5 py-0.5 font-mono text-xs text-ink-muted">
                    E1
                  </span>
                  <p className="text-sm text-ink-muted">
                    Sender domain registered 4 days ago, mimics a known bank.
                  </p>
                </div>
                <div className="flex items-start gap-2">
                  <span className="mt-0.5 rounded-sm border border-line-strong bg-surface-raised px-1.5 py-0.5 font-mono text-xs text-ink-muted">
                    E2
                  </span>
                  <p className="text-sm text-ink-muted">
                    Message asks for a UPI PIN to &ldquo;receive&rdquo; a refund.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Credibility row */}
      <section className="border-b border-line px-6 py-14 sm:px-10 lg:px-16">
        <div className="grid gap-8 sm:grid-cols-3">
          {CREDIBILITY.map(({ Icon, label, body }) => (
            <div key={label} className="flex flex-col gap-2.5">
              <Icon className="h-5 w-5 text-accent" />
              <span className="font-display text-sm text-ink">{label}</span>
              <p className="max-w-[32ch] text-sm text-ink-muted">{body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="border-b border-line px-6 py-20 sm:px-10 lg:px-16">
        <h2 className="font-display text-2xl font-semibold text-ink sm:text-3xl">How it works</h2>
        <ol className="mt-10 grid gap-10 sm:grid-cols-3">
          {STEPS.map((step) => (
            <li key={step.n} className="flex flex-col gap-2">
              <span className="font-mono text-sm text-accent">{step.n}</span>
              <span className="font-display text-base text-ink">{step.label}</span>
              <p className="max-w-[34ch] text-sm text-ink-muted">{step.body}</p>
            </li>
          ))}
        </ol>
      </section>

      {/* Closing CTA */}
      <section className="px-6 py-20 text-center sm:px-10 lg:px-16">
        <h2 className="font-display text-3xl font-semibold text-balance text-ink sm:text-4xl">
          Got a message you&rsquo;re not sure about?
        </h2>
        <button
          type="button"
          onClick={() => navigate('/check')}
          className="group mt-8 inline-flex items-center gap-2 rounded-md bg-accent px-6 py-3.5 font-display text-sm font-semibold text-accent-ink transition hover:bg-accent-strong active:scale-[0.99]"
        >
          Investigate a message
          <IconArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
        </button>
      </section>
    </main>
  )
}
