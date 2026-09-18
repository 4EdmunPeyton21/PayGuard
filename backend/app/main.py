"""PayGuard Core API.

Routes:
  POST /api/v1/analyze       — Sync analysis endpoint producing SafetyReport JSON
  GET  /cases/{id}           — Retrieve persisted SafetyReport by case ID
  GET  /api/v1/cases/{id}    — Alias for /cases/{id}
  GET  /cases/{id}/trace     — Retrieve ordered tool execution trace from DynamoDB
  GET  /api/v1/cases/{id}/trace — Alias for /cases/{id}/trace
  GET  /healthz              — Service & DynamoDB health check
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.agent.investigator import _extract_urls, investigate
from app.agent.narrator import get_recommended_actions, narrate
from app.kb.loader import kb
from app.risk.engine import evaluate_ledger
from app.schemas.case import AnalyzeRequest, NormalisedCase
from app.schemas.evidence import Signal
from app.schemas.report import SafetyReport
from app.store.dynamo import get_case_report, get_case_trace, get_table, save_case_investigation

app = FastAPI(
    title="PayGuard API",
    version="1.0.0",
    description="Evidence-first financial scam investigation engine for Indian payment contexts.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> Dict[str, str]:
    """Health check endpoint checking DynamoDB connectivity."""
    db_status = "ok"
    try:
        table = get_table()
        table.load()
    except Exception as exc:
        db_status = f"error: {exc}"
    return {"status": "ok", "dynamodb": db_status}


@app.post("/api/v1/analyze", response_model=SafetyReport)
def analyze_case(request: AnalyzeRequest) -> SafetyReport:
    """Synchronous case analysis endpoint.

    Ingests message text / context -> NormalisedCase -> Investigator agent loop
    -> Risk Engine -> Narrator (with citation/lint validation) -> DynamoDB persistence.
    """
    if not request.text and not request.payment_context and not request.image_ref:
        raise HTTPException(
            status_code=400,
            detail="At least one input (text, payment_context, or image_ref) must be provided.",
        )

    t0 = time.perf_counter()
    case_id = f"c_{uuid.uuid4().hex[:8]}"

    # Ingest & normalise
    text = request.text or ""
    urls = _extract_urls(text)
    input_types = []
    if text:
        input_types.append("text")
    if urls:
        input_types.append("url")
    if not input_types:
        input_types = ["text"]

    case = NormalisedCase(
        case_id=case_id,
        input_types=input_types,
        text=text,
        text_source="user",
        urls=urls,
        payment_context=request.payment_context,
        image_ref=request.image_ref,
    )

    # Execute investigation loop
    inv_result = investigate(case, max_tool_calls=request.options.max_tool_calls)

    # Evaluate risk score & level via deterministic risk engine
    risk_res = evaluate_ledger(inv_result.ledger)

    # Extract claimed institution identity if detected
    claimed_entity: Optional[str] = None
    for e in inv_result.ledger.items:
        if e.signal == Signal.IMPERSONATION_CLAIM and e.quote:
            claimed_entity = e.quote
            break

    # Narrate via LLM with citation & certainty lint validators
    narration = narrate(
        ledger=inv_result.ledger,
        level=risk_res.level.value,
        claimed_entity=claimed_entity,
    )

    # Assemble recommended actions from KB advice.yaml
    signals = [e.signal for e in inv_result.ledger.items]
    actions = get_recommended_actions(signals)
    latency_ms = int((time.perf_counter() - t0) * 1000)

    report = SafetyReport(
        case_id=case_id,
        risk_level=risk_res.level.value,
        risk_score=float(risk_res.score),
        headline=narration.headline,
        why=narration.why,
        evidence=list(inv_result.ledger.items),
        recommended_actions=actions,
        unverified=["PayGuard could not confirm who actually sent this message."],
        rules_fired=risk_res.rules_fired,
        policy_version=risk_res.policy_version,
        kb_version=kb.version,
        model="gpt-oss-20b" if not narration.via_fallback else "template_fallback",
        tool_calls=inv_result.tool_calls,
        latency_ms=latency_ms,
    )

    # Persist to DynamoDB Single Table
    save_case_investigation(case_id, case, report, inv_result.trace)

    return report


@app.get("/cases/{case_id}", response_model=SafetyReport)
@app.get("/api/v1/cases/{case_id}", response_model=SafetyReport)
def get_case(case_id: str) -> SafetyReport:
    """Retrieve the stored SafetyReport for a case."""
    report = get_case_report(case_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")
    return report


@app.get("/cases/{case_id}/trace")
@app.get("/api/v1/cases/{case_id}/trace")
def get_trace(case_id: str) -> Dict[str, Any]:
    """Retrieve the full investigation tool chain and execution trace."""
    trace = get_case_trace(case_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")
    return {"case_id": case_id, "trace": trace}
