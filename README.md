# PayGuard

**Evidence-first scam investigation for Indian payment contexts.**

PayGuard doesn't just classify a message as "safe" or "risky" — it investigates it like an
analyst would. Paste in an SMS, WhatsApp message, email, or a screenshot, and PayGuard scans it
for tells, gathers evidence tool-by-tool (link inspection, domain/entity checks, UPI/QR
analysis), scores it against a deterministic, auditable risk policy, and explains its verdict
with every claim traced back to a quoted piece of evidence — never a guess.

> Don't trust it. Investigate it.

---

## Table of contents

- [How it works](#how-it-works)
- [Core concepts](#core-concepts)
- [Tech stack](#tech-stack)
- [Repository structure](#repository-structure)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [API reference](#api-reference)
- [Testing](#testing)
- [Evaluation harness](#evaluation-harness)
- [Development workflow](#development-workflow)
- [Deployment status](#deployment-status)
- [Project status & roadmap](#project-status--roadmap)
- [License](#license)

---

## How it works

```
 Message / screenshot
        │
        ▼
 ┌─────────────┐   OCR (rapidocr) if the input is an image
 │   Ingest    │   → NormalisedCase (text, urls, qr_payloads, payment_context)
 └──────┬──────┘
        ▼
 ┌─────────────┐   Agent decides which tools still need running:
 │ Investigator│   signal_scan · url_inspect · entity_domain_check ·
 │  (agent     │   pattern_match · qr_decode · upi_analyze
 │   loop)     │   Each tool call is cached by an argument hash and checked
 └──────┬──────┘   for provenance (no citing evidence a tool didn't produce).
        ▼
 ┌─────────────┐   Every finding becomes an Evidence item — observed fact +
 │  Evidence   │   interpretation + direction (risk/benign/neutral) + strength
 │   Ledger    │   (HIGH claims must carry a quote or a knowledge-base ref).
 └──────┬──────┘
        ▼
 ┌─────────────┐   Deterministic, YAML-driven policy (risk/policy_v1.yaml)
 │ Risk Engine │   scores the ledger → LOW_CONCERN / CAUTION / HIGH_RISK
 └──────┬──────┘   No LLM call in the scoring path — same evidence, same score.
        ▼
 ┌─────────────┐   LLM narrates the verdict; a citation + certainty linter
 │  Narrator   │   validates every claim against the ledger and retries or
 └──────┬──────┘   falls back to a deterministic template if it can't pass.
        ▼
 SafetyReport (persisted to DynamoDB) → React UI (live trace via SSE)
```

Everything the pipeline concludes traces back to something it actually observed. If a tool
can't back a claim with a quote or a knowledge-base reference, that claim can't be marked
`HIGH` strength — this is enforced by a Pydantic validator on `Evidence`, not a convention.

## Core concepts

| Concept | What it is |
|---|---|
| `NormalisedCase` | The ingested input, normalized: text, extracted URLs, QR payloads, payment context. |
| `Signal` | An enum of the ~30 tells the system recognizes (`otp_request`, `lookalike_domain`, `upi_collect_request`, ...). |
| `Evidence` | One observed fact: which tool found it, which `Signal` it maps to, a quote/kb-ref, direction, strength, confidence. |
| `EvidenceLedger` | The append-only collection of `Evidence` gathered for a case — the single source of truth the risk engine and narrator both read from. |
| `ToolRegistry` | Dispatches tool calls with argument-hash caching and provenance checks, so a tool can't be credited with evidence it didn't produce. |
| `SafetyReport` | The final output: risk level/score, headline, cited claims, recommended actions, and the full evidence list. |

## Tech stack

**Backend** — Python 3.11, FastAPI, Pydantic v2, boto3 (DynamoDB), Strands Agents SDK,
RapidOCR, OpenCV, `qrcode`, Server-Sent Events for live streaming.

**Frontend** — React 19, TypeScript, Vite, Tailwind CSS v4.

**Infrastructure (local)** — DynamoDB Local + LocalStack via Docker Compose.

**Evaluation** — pandas / scikit-learn / matplotlib, a 4-arm comparison harness
(deterministic baseline, baseline LLM, agent+tools, fine-tuned).

## Repository structure

```
backend/app/
  agent/        investigator loop, fallback loop, gap checker, narrator, prompts
  ingest/       OCR, screenshot/URL extraction, QR decoding
  kb/           knowledge base (entities, lexicon, patterns, advice) + loader
  llm/          LLM provider abstraction (NVIDIA / Bedrock / OpenAI / Ollama) + cache
  risk/         deterministic risk-scoring engine + YAML policy
  schemas/      Pydantic models (case, evidence, report, tools)
  store/        DynamoDB single-table persistence
  tools/        signal_scan, url_inspect, entity_domain_check, pattern_match, qr_decode,
                upi_analyze, redirect_resolve (flagged off) + the ToolRegistry
  validate/     citation and certainty linters for narrator output
  main.py       FastAPI app & routes
backend/tests/  pytest unit tests (one file per module, 18 files)

frontend/src/
  pages/        LandingPage, InputPage, TracePage, CasePage
  api.ts        typed fetch/SSE client for the backend
  icons.tsx     shared SVG icon set

eval/           4-arm evaluation harness, dataset, metrics, results
scripts/        create_tables.py, seed_kb.py, make_dataset.py, smoke_llm.py, qr_refund_demo.py
plans/          design docs: deliverables list, architecture decisions
infra/          docker-compose.yml (local infra) + template.yaml (SAM — not yet built, see below)
results/        RESULTS.md — evaluation findings
```

## Getting started

### Prerequisites

- Python 3.11+
- Node.js 20+
- Docker (for local DynamoDB + LocalStack)
- An API key for at least one supported LLM provider (NVIDIA NIM by default; Bedrock, OpenAI,
  and Ollama are also supported — see [Configuration](#configuration))

### 1. Clone and install dependencies

```bash
git clone https://github.com/4EdmunPeyton21/PayGuard.git
cd PayGuard

pip install -r backend/requirements.txt

cd frontend
npm install
cd ..
```

### 2. Start local infrastructure

```bash
docker compose up -d
```

This starts DynamoDB Local (port 8000) and LocalStack's S3 (port 4566) — no AWS account
needed for local development.

### 3. Configure environment

```bash
cp .env.example .env
```

Fill in your LLM provider's API key at minimum. See [Configuration](#configuration) for the
full list of settings and their defaults.

### 4. Create the DynamoDB table

```bash
python scripts/create_tables.py
```

### 5. Run the backend

```bash
cd backend
uvicorn app.main:app --reload --port 8080
```

The API is now live at `http://localhost:8080` (interactive docs at `/docs`).
Check `http://localhost:8080/healthz` to confirm DynamoDB connectivity.

### 6. Run the frontend

```bash
cd frontend
npm run dev
```

Open `http://localhost:5173`. The landing page is at `/`, the tool itself at `/check`.

## Configuration

All settings are read from environment variables (or a `.env` file) via `backend/app/config.py`.
Everything has a sane local-dev default except the LLM API key.

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `nvidia` | `nvidia`, `bedrock`, `openai`, or `ollama` |
| `LLM_BASE_URL` | NVIDIA NIM endpoint | OpenAI-compatible base URL |
| `LLM_API_KEY` | — | **Required.** Your provider's API key |
| `LLM_MODEL` | `openai/gpt-oss-20b` | Model identifier |
| `LLM_TEMPERATURE` | `0.0` | Sampling temperature |
| `LLM_CACHE` | `true` | Cache LLM responses by argument hash |
| `AGENT_RUNTIME` | `simple` | `simple` or `strands` |
| `MAX_TOOL_CALLS` | `6` | Cap on tool calls per investigation |
| `RISK_POLICY` | `risk_policy_v1` | Which policy file to load from `backend/app/risk/` |
| `AWS_REGION` | `us-west-2` | Region for DynamoDB/S3 clients |
| `DDB_TABLE` | `PayGuardCases` | DynamoDB table name |
| `DDB_ENDPOINT_URL` | `http://localhost:8000` | Set to unset/blank to use real AWS DynamoDB |
| `S3_BUCKET` | `payguard-uploads` | Bucket for uploaded screenshots |
| `S3_ENDPOINT_URL` | `http://localhost:4566` | Set to unset/blank to use real AWS S3 |
| `CASE_TTL_DAYS` | `7` | How long case records are retained |
| `MAX_UPLOAD_MB` | `5` | Screenshot upload size limit |

## API reference

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/analyze` | Synchronous analysis — returns the full `SafetyReport` |
| `POST` | `/api/v1/analyze/stream` | Server-Sent Events — live `ingest → tool_start → tool_result → risk → report` |
| `POST` | `/api/v1/ocr` | Upload a screenshot, get back extracted text to confirm before analysis |
| `GET` | `/cases/{id}` (+ `/api/v1/cases/{id}`) | Retrieve a persisted `SafetyReport` |
| `GET` | `/cases/{id}/trace` (+ `/api/v1/cases/{id}/trace`) | Retrieve the ordered tool-execution trace |
| `GET` | `/healthz` | Service + DynamoDB health check |

Full interactive documentation is auto-generated by FastAPI at `/docs` when the backend is
running.

## Testing

```bash
pytest
```

18 test files under `backend/tests/unit/`, one per module (API routes, risk engine, tool
registry, KB loader, narrator, fallback loop, gap checker, schemas, and each individual tool).
Configuration lives in `pyproject.toml` (`pythonpath = ["backend"]`, so tests import `app.*`
directly).

Linting and type-checking (not yet wired into CI — run manually before committing):

```bash
ruff check .
mypy backend/app
```

`ruff` is configured for line-length 100, target Python 3.11, with `E`, `F`, `W`, `I`, `B`
rule sets enabled (`pyproject.toml`).

## Evaluation harness

PayGuard is evaluated across four "arms" on a shared 90-case test dataset
(`eval/dataset/cases.jsonl`):

- **Arm 0** — deterministic pipeline (no LLM in the loop)
- **Arm 1** — baseline: raw LLM call, no tools
- **Arm 2** — agent with tool access
- **Arm 3** — fine-tuned model (not yet run)

```bash
python eval/run_eval.py --arm arm0 --split test
```

Latest results (`results/RESULTS.md`, mean over 3 runs):

| Arm | Accuracy | False Positive Rate | Evidence Precision |
|---|---|---|---|
| Arm 0 (Deterministic) | 97.78% | 0.00% | 100.00% |
| Arm 1 (Baseline LLM) | 45.56% | 100.00% | 0.00% |
| Arm 2 (Agent + Tools) | 86.67% | 0.00% | 100.00% |

See `results/RESULTS.md` for confidence intervals, the hard-negative subset breakdown, and
known limitations (both LLM arms depend on a reachable LLM endpoint; without one they exercise
their designed fallback paths rather than live model judgment).

## Development workflow

- **Branching**: work off `main`; this is currently a solo/hackathon project without a
  protected-branch or PR-review process configured yet.
- **Commits**: conventional-ish prefixes (`feat`, `fix`, `style`, `chore`) with a scope, e.g.
  `feat(frontend): add marketing landing page`.
- **Before committing**: run `pytest`, `ruff check .`, and `mypy backend/app`. There is no CI
  pipeline yet — these checks are manual (see [Roadmap](#project-status--roadmap)).
- **Design docs**: architecture decisions and the full deliverables breakdown live in
  `plans/payguard-plan.md` and `plans/payguard-deliverables.md`.

## Deployment status

**Not yet deployed.** Everything above runs locally against Docker-hosted DynamoDB/S3. The
planned path to AWS (Lambda container image + API Gateway + Amplify, per
`plans/payguard-deliverables.md` D27) is scoped but not built — `infra/template.yaml` is
currently an empty placeholder. Given the backend's SSE streaming endpoint, a container run on
AWS App Runner (rather than Lambda + API Gateway, which handles long-lived streaming responses
poorly) is the more likely production shape when this is picked up.

## Project status & roadmap

This project follows the deliverables plan in `plans/payguard-deliverables.md` (D1 through D30,
tagged `CORE` or `CUTTABLE`). Completed so far: ingest, knowledge base, agent investigator loop,
tool registry with caching/provenance, risk engine, narrator with citation/lint validation,
FastAPI server with SSE streaming, DynamoDB persistence, React UI, QR/UPI tooling, OCR, and the
4-arm evaluation harness. Outstanding `CUTTABLE` items include AWS deployment (D27) and Bedrock
Guardrails (D30).

## License

Apache License 2.0 — see [`LICENSE`](LICENSE).
