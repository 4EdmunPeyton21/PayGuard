# PayGuard — Build Ladder

26 deliverables. Each one is 30–90 minutes, ends in something you can run, and requires you to hold **only its own inputs and outputs** in your head.

**Working rules**

1. One deliverable open at a time. Finish it, commit it, close the tab.
2. Never read ahead more than one rung. The plan doc is a reference, not a reading assignment.
3. If a deliverable takes >2× its estimate, ship the ugly version and move on. Note the debt, don't fix it now.
4. Every deliverable has a **Done when** you can literally run. If you can't run it, it isn't done.
5. **Don't** lines are scope guards. They are the things you will be tempted to build early. Resist.

**Every deliverable follows this template:**

> **D#: Name** · `CORE | CUTTABLE` · ~time
> **Build** — the files you touch
> **Contract** — what goes in, what comes out (this is all you need to know about the rest of the system)
> **Done when** — a command and its expected output
> **Don't** — the scope trap

---

# Phase A — A working product with no AI in it

*Checkpoint: after D10 you have a system that takes a scam SMS and returns a risk level with evidence, plus measured numbers. If everything after this fails, you still have a demo.*

---

**D1: Repo skeleton + config** · `CORE` · ~30 min
**Build** — folder tree, `config.py` (pydantic-settings), `.env.example`, `docker-compose.yml` (dynamodb-local + localstack), `ruff`/`pytest` set up.
**Contract** — in: env vars. out: a `settings` object anything can import.
**Done when** — `python -c "from app.config import settings; print(settings.llm_model)"` prints your model name, and `docker compose up -d` gives you two healthy containers.
**Don't** — write any app logic. No FastAPI yet.

---

**D2: LLM smoke test** · `CORE` · ~30 min
**Build** — `app/llm/provider.py` with `get_model()`, plus `scripts/smoke_llm.py`.
**Contract** — in: env vars. out: a model object, and proof it answers.
**Done when** — the script prints a one-word completion from `openai/gpt-oss-20b` via NIM, **and** a second run with two dummy tools (`add`, `multiply`) shows the model correctly emitting a tool call.
**Don't** — build the investigator. This is a 40-line throwaway that proves your key and tool-calling work. If tool calling fails here, you learn it on hour 1 instead of hour 20.

---

**D3: Schemas** · `CORE` · ~45 min
**Build** — `schemas/evidence.py`, `schemas/case.py`, the `Signal` enum.
**Contract** — in: nothing. out: `Evidence`, `NormalisedCase`, `Signal`, `EvidenceLedger`.
**Done when** — `pytest tests/unit/test_schemas.py` passes: a valid Evidence constructs, an unknown `signal` string raises, and `strength="HIGH"` without a `quote` or `kb_ref` raises.
**Don't** — add fields "we might need." Start with the ones in the plan; adding a field later costs 30 seconds.

---

**D4: Knowledge base v0** · `CORE` · ~45 min
**Build** — `kb/entities.yaml` (10 entities: HDFC, SBI, ICICI, Axis, PhonePe, Paytm, Google Pay, Amazon, Flipkart, India Post), `kb/loader.py`, `kb_version` content hash.
**Contract** — in: nothing. out: `kb.resolve_entity("hdfc") -> Entity | None`, `kb.version -> str`.
**Done when** — `pytest` proves `resolve_entity("HDFC Bank")`, `resolve_entity("hdfc")` and `resolve_entity("एचडीएफसी")` all return the same entity id, and an unknown string returns `None`.
**Don't** — go past 10 entities. You'll add more on day 3 in five minutes.

---

**D5: Tool — `signal_scan`** · `CORE` · ~60 min
**Build** — `tools/signal_scan.py`, `kb/lexicon.yaml`.
**Contract** — in: `text: str`. out: list of `{signal, quote, span, confidence}`.
**Done when** — on your fake-KYC demo string it returns `urgency_language`, `threat_of_consequence`, `credential_request`; on a real transaction alert it returns `no_actionable_request` and nothing else. Every returned `quote` satisfies `text[span[0]:span[1]] == quote` (assert this in the test).
**Don't** — use an LLM. This is regex and a word list. Add 5 Hinglish phrases and stop.

---

**D6: Tool — `url_inspect`** · `CORE` · ~60 min
**Build** — `tools/url_inspect.py`.
**Contract** — in: `url: str`. out: parsed structure + `signals`.
**Done when** — the nasty fixture set passes: `hdfcbank.com.verify-kyc.ru` → `lookalike_domain` + `brand_token_outside_domain`; `192.168.1.1/hdfc` → `ip_address_host`; `bit.ly/x` → `link_shortener`; `sbi.co.in` → clean (this one catches eTLD bugs); a Cyrillic lookalike → `punycode_host`.
**Don't** — make a single network call. No WHOIS, no fetching, no DNS.

---

**D7: Tool — `entity_domain_check`** · `CORE` · ~30 min
**Build** — `tools/entity_domain_check.py`.
**Contract** — in: `claimed_entity: str`, `domains: list[str]`. out: `{match, official_domains, entity_in_kb, kb_ref}`.
**Done when** — `("HDFC Bank", ["hdfc-secure-kyc.in"])` → `match=false`; `("HDFC Bank", ["hdfcbank.com"])` → `match=true`; `("Nonexistent Bank", [...])` → `entity_in_kb=false`.
**Don't** — let anything except the YAML supply an official domain. Ever.

---

**D8: Tool — `pattern_match`** · `CORE` · ~45 min
**Build** — `tools/pattern_match.py`, `kb/patterns.yaml` with 6 patterns (fake KYC, OTP harvesting, fake refund, fake delivery fee, QR manipulation, job-fee).
**Contract** — in: `signals: list[str]`. out: matched patterns + which signals fired and which were missing.
**Done when** — the fake-KYC signal set matches `fake_kyc` and nothing else; an empty signal set matches nothing.
**Don't** — embeddings. Don't install a vector DB. Set matching over YAML.

---

**D9: Risk engine** · `CORE` · ~60 min
**Build** — `risk/engine.py`, `risk/policy_v1.yaml`.
**Contract** — in: `EvidenceLedger`. out: `{level, score, rules_fired}`.
**Done when** — `tests/unit/test_risk.csv` (signal set → expected level) passes, including: the fake-KYC set → `HIGH_RISK` via gate; a lone `urgency_language` → `LOW_CONCERN`; `domain_verified_official` + `urgency_language` → capped at `LOW_CONCERN` by the FP guard.
**Don't** — hardcode weights in Python. If it isn't in the YAML you can't tune it on day 3.

---

**D10: Arm 0 — the whole system, no LLM** · `CORE` · ~45 min
**Build** — `eval/arms/arm0_deterministic.py`: run all tools in fixed order → ledger → risk engine → template-rendered report.
**Contract** — in: `NormalisedCase`. out: `SafetyReport`.
**Done when** — `python -m eval.arms.arm0_deterministic --text "<your fake KYC SMS>"` prints `HIGH_RISK` with 4+ evidence items and recommended actions pulled from `advice.yaml`.
**Don't** — skip the template report renderer. It's 30 lines and it becomes your fallback when the LLM fails on stage.

🏁 **You now have a working product.** Everything after this makes it smarter, not functional.

---

**D11: Dataset v0 (40 cases) + eval harness** · `CORE` · ~90 min
**Build** — `eval/dataset/cases.jsonl` (25 scam across 6 categories, 15 legitimate including 5 hard negatives), `eval/run_eval.py`, `eval/metrics.py`.
**Contract** — in: `--arm`, `--split`. out: `results/<run_id>/results.jsonl` + printed metrics table.
**Done when** — `python -m eval.run_eval --arm arm0 --split all` prints accuracy, FPR, FNR, evidence precision/recall and a confusion matrix.
**Don't** — chase 150 cases now. 40 is enough to find bugs. You expand on day 3.

---

**D12: Arm 1 — bare LLM baseline** · `CORE` · ~30 min
**Build** — `eval/arms/arm1_baseline_llm.py`: one prompt, message in, `{level, reasons}` JSON out.
**Contract** — in: `NormalisedCase`. out: `SafetyReport` (evidence list empty).
**Done when** — it runs over all 40 cases and lands in the metrics table next to Arm 0.
**Don't** — improve this prompt. It's supposed to be the naive thing everyone else builds. Making it good weakens your comparison and wastes your time.

---

# Phase B — Make it agentic

*Checkpoint: after D16 you have the actual contribution — adaptive investigation with validated explanations, and three arms of numbers.*

---

**D13: Tool registry** · `CORE` · ~45 min
**Build** — `tools/registry.py`: name → `{callable, input schema, output schema, description}`, plus the arg-hash cache and the argument-provenance check.
**Contract** — in: tool name + args dict. out: validated output model, or a structured rejection.
**Done when** — calling the same tool twice with identical args hits the cache (assert one execution), and calling `url_inspect` with a URL not present in the case is rejected with a correction message.
**Don't** — couple this to Strands. It's a plain dict and a dispatch function. Both agent runtimes will wrap it.

---

**D14: Agent loop v1** · `CORE` · ~90 min
**Build** — `agent/investigator.py` (Strands), `agent/prompts.py`.
**Contract** — in: `NormalisedCase`. out: `(EvidenceLedger, trace)`.
**Done when** — on the fake-KYC case it makes 4–5 tool calls and the trace shows it *chose* the order; on the legitimate transaction alert it makes ≤3 and stops. Budget of 6 is enforced.
**Don't** — build the narrator yet. This deliverable ends at a populated ledger. If Strands fights you for more than 45 minutes, write `agent/fallback_loop.py` instead and move on — you can come back.

---

**D15: Gap checker** · `CORE` · ~30 min
**Build** — `agent/gap_checker.py`.
**Contract** — in: `(case, ledger)`. out: `PASS` or a forced next tool call.
**Done when** — a case with a URL that the agent never inspected gets one forced `url_inspect` call, and the test asserts the ledger gains that evidence.
**Don't** — make it smart. It's 5 `if` statements. Its whole job is a coverage floor.

---

**D16: Narrator + validators** · `CORE` · ~75 min
**Build** — `agent/narrator.py`, `validate/citations.py`, `validate/lint.py`, template fallback.
**Contract** — in: `(ledger, level)`. out: validated `{headline, why[]}`.
**Done when** — three tests pass: a narration citing `E99` (nonexistent) is rejected; a narration containing "this is definitely a scam" is rejected; after `NARRATOR_MAX_RETRIES` the template fallback produces a complete valid report.
**Don't** — let the narrator see the raw message text. It gets the ledger only. That's the whole point.

---

**D17: Arm 2 + first real comparison** · `CORE` · ~45 min
**Build** — `eval/arms/arm2_agent_tools.py`, wire into `run_eval`.
**Contract** — in: `--arm arm2`. out: same metrics shape as the others.
**Done when** — one table shows Arms 0/1/2 on accuracy, FPR, FNR, evidence recall, mean tool calls. Run it 3× and record the spread.
**Don't** — tune anything yet based on these numbers. Look, note what's broken, keep going. Tuning is D23.

🏁 **You now have a defensible experiment.** Everything after this is presentation.

---

# Phase C — The face

*Checkpoint: after D21 you can demo it.*

---

**D18: FastAPI + storage** · `CORE` · ~60 min
**Build** — `main.py` with `POST /api/v1/analyze`, `GET /cases/{id}`, `GET /cases/{id}/trace`; `store/dynamo.py`; `scripts/create_tables.py`.
**Contract** — in: JSON request. out: `SafetyReport` JSON, persisted.
**Done when** — `curl` with the fake-KYC text returns the full report, and a second `curl` to `/cases/{id}/trace` returns the tool chain from DynamoDB Local.
**Don't** — add auth, uploads, or SSE. One sync endpoint.

---

**D19: SSE streaming** · `CORE` · ~45 min
**Build** — `POST /api/v1/analyze/stream`, emitting `ingest` → `tool_start` → `tool_result` → `risk` → `report`.
**Contract** — in: same request. out: an event stream.
**Done when** — `curl -N` shows events arriving one at a time as the agent works, not all at the end.
**Don't** — skip this to save time. The live trace is 80% of why the demo lands.

---

**D20: React — input + verdict** · `CORE` · ~90 min
**Build** — Vite app, `/` (paste message + optional payment context + Check), `/case/:id` (level chip, headline, why-claims, actions, "could not verify" block).
**Contract** — in: the API. out: two screens.
**Done when** — you can paste the SMS in a browser and see HIGH_RISK with evidence. Colour is never the only signal — icon + word too.
**Don't** — install a component library. Tailwind and three files.

---

**D21: React — trace screen** · `CORE` · ~75 min
**Build** — `/case/:id/trace`, vertical timeline fed by SSE, one card per tool call (args, latency, raw JSON collapsible), then the risk-engine card (score, rules fired, thresholds).
**Contract** — in: the SSE stream. out: the screen that wins the hackathon.
**Done when** — you run a case and watch the cards appear one by one in real time.
**Don't** — animate anything elaborate. Appearing in sequence is enough.

---

# Phase D — Differentiators and finish

---

**D22: QR + UPI tools** · `CORE` · ~75 min
**Build** — `tools/qr_decode.py`, `tools/upi_analyze.py`, and the refund-QR demo case.
**Contract** — in: image path / UPI payload + payment context. out: parsed fields + mismatch signals.
**Done when** — your generated "scan to receive ₹2,000 refund" QR decodes to a collect request to a personal VPA and produces `upi_payee_mismatch` + `upi_amount_mismatch`.
**Don't** — build a camera scanner in the browser. File upload is fine for a demo.

---

**D23: OCR path** · `CUTTABLE` · ~60 min
**Build** — `ingest/ocr.py`, upload endpoint, "confirm extracted text" step in the UI.
**Contract** — in: image. out: text + confidence, emitting `ocr_low_confidence` when weak.
**Done when** — a rendered SMS screenshot produces text close enough that `signal_scan` finds the same signals as the pasted version.
**Don't** — fight OCR quality. If `rapidocr` is poor on your screenshots after 45 minutes, keep the confirm-text step, demo with paste, and say OCR is a known limitation. That's a fine answer.

---

**D24: Dataset to 150 + adversarial** · `CORE` · ~90 min
**Build** — expand to 150 cases; add 20 adversarial (10 scary-but-legitimate, 10 polite-but-scam) and 3 prompt-injection cases; split 60 dev / 90 test.
**Contract** — in: seed cases. out: `cases.jsonl` with splits.
**Done when** — `run_eval --split dev` and `--split test` both work, and the 3 injection cases do not flip the verdict.
**Don't** — trust LLM-generated cases unreviewed. Read every one.

---

**D25: Tune and report** · `CORE` · ~75 min
**Build** — adjust `policy_v1.yaml` **on dev only**; `eval/report.py` → `results/RESULTS.md` with bootstrap CIs.
**Contract** — in: dev results. out: tuned policy + a test-split table you can put on a slide.
**Done when** — `RESULTS.md` has all four arms (Arm 3 marked "not run, see §15"), mean ± std over 3 runs, and FPR broken out for the hard-negative subset.
**Don't** — touch the policy after you've looked at test results. Write down the dev-only rule and honour it; it's the difference between a result and a story.

---

**D26: Bedrock switch + AWS demo moment** · `CORE` · ~45 min
**Build** — verify Bedrock model access, second `.env.bedrock`, confirm identical output.
**Contract** — in: three changed env vars. out: same report, different provider.
**Done when** — you run the same case twice, NIM then Bedrock, and get the same risk level and evidence. Screenshot both traces.
**Don't** — leave this to day 3 evening. Check model access on **day 1** — access enablement can take time and you don't want that surprise at hour 68.

---

**Optional rungs, in priority order if you're ahead**

- **D27: SAM template + deploy** · `CUTTABLE` · ~90 min — Lambda container image + API Gateway + Amplify. Only if Phase D is done and rehearsed.
- **D28: Incident-response flow** · `CUTTABLE` · ~45 min — "I already clicked" → advice from `advice.yaml`. Cheap and demos well.
- **D29: Trajectory collector** · `CUTTABLE` · ~30 min — dump successful Arm 2 runs as SFT-format JSONL. Makes your fine-tuning slide concrete.
- **D30: Bedrock Guardrails** · `CUTTABLE` · ~30 min — PII blocking on narration output.

---

## If you fall behind

Cut in this order: D27 → D23 → D22 → D19. Never cut D9, D11, D17 or D25 — those four are the entire scientific claim, and a project with numbers and no screenshots beats a project with screenshots and no numbers.

## The two sentences to keep on a sticky note

> Right now I am building **D#**. Its input is ___ and its output is ___.

> Everything else is already decided and written down. I do not need to think about it.
