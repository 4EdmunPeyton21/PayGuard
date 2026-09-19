"""PayGuard Core API.

Routes:
  POST /api/v1/analyze          — Sync analysis endpoint producing SafetyReport JSON
  POST /api/v1/analyze/stream   — SSE: ingest -> tool_start -> tool_result -> risk -> report
  POST /api/v1/ocr               — Upload a screenshot, get back OCR'd text to confirm
  GET  /cases/{id}           — Retrieve persisted SafetyReport by case ID
  GET  /api/v1/cases/{id}    — Alias for /cases/{id}
  GET  /cases/{id}/trace     — Retrieve ordered tool execution trace from DynamoDB
  GET  /api/v1/cases/{id}/trace — Alias for /cases/{id}/trace
  GET  /healthz              — Service & DynamoDB health check
"""
from __future__ import annotations

import io
import json
import os
import queue
import tempfile
import threading
import time
import uuid
from typing import Any, Callable, Dict, Iterator, Optional, Tuple

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from PIL import Image, UnidentifiedImageError

from app.agent.investigator import _extract_urls, investigate
from app.agent.narrator import get_recommended_actions, narrate
from app.config import settings
from app.ingest.ocr import OcrResult, extract_text
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


@app.post("/api/v1/ocr", response_model=OcrResult)
async def ocr_upload(file: UploadFile = File(...)) -> OcrResult:  # noqa: B008 (FastAPI idiom)
    """Extract text from an uploaded screenshot for the user to confirm (D23).

    The raw upload is never persisted: re-encoded through Pillow (drops EXIF,
    flattens any multi-frame image) into a throwaway temp file for OCR, then
    deleted. Low-confidence extractions are flagged so the UI can prompt the
    user to review/edit before the text is investigated.
    """
    contents = await file.read()
    if len(contents) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {settings.max_upload_mb}MB upload limit.",
        )

    try:
        image = Image.open(io.BytesIO(contents))
        image.load()
    except UnidentifiedImageError as exc:
        raise HTTPException(
            status_code=400, detail="Uploaded file is not a readable image."
        ) from exc

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            image.convert("RGB").save(tmp, format="PNG")
            tmp_path = tmp.name
        return extract_text(tmp_path)
    finally:
        if tmp_path:
            os.unlink(tmp_path)


def _build_case(request: AnalyzeRequest) -> Tuple[str, NormalisedCase]:
    """Ingest & normalise an AnalyzeRequest into a NormalisedCase."""
    case_id = f"c_{uuid.uuid4().hex[:8]}"
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
    return case_id, case


def _run_pipeline(
    case_id: str,
    case: NormalisedCase,
    max_tool_calls: int,
    t0: float,
    on_event: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> SafetyReport:
    """Investigator -> Risk Engine -> Narrator -> DynamoDB persistence.

    Shared by the sync /analyze endpoint and the SSE /analyze/stream
    endpoint; on_event (if given) is fired with ("tool_start"/"tool_result"
    from the agent loop, and "risk" once the risk engine has scored the
    ledger) so a caller can stream progress live instead of waiting for
    the full report.
    """
    emit = on_event or (lambda *_a, **_kw: None)

    inv_result = investigate(case, max_tool_calls=max_tool_calls, on_event=on_event)

    risk_res = evaluate_ledger(inv_result.ledger)
    emit(
        "risk",
        {
            "level": risk_res.level.value,
            "score": float(risk_res.score),
            "rules_fired": risk_res.rules_fired,
        },
    )

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
    case_id, case = _build_case(request)
    return _run_pipeline(case_id, case, request.options.max_tool_calls, t0)


def _sse(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@app.post("/api/v1/analyze/stream")
def analyze_case_stream(request: AnalyzeRequest) -> StreamingResponse:
    """SSE analysis endpoint — same pipeline as /analyze, emitted live.

    Event sequence: ingest -> tool_start -> tool_result (repeated per tool
    call) -> risk -> report. The pipeline runs on a background thread; a
    queue.Queue bridges its on_event callbacks to this generator so events
    reach the client as the agent works, not all at once at the end.
    """
    if not request.text and not request.payment_context and not request.image_ref:
        raise HTTPException(
            status_code=400,
            detail="At least one input (text, payment_context, or image_ref) must be provided.",
        )

    def gen() -> Iterator[str]:
        t0 = time.perf_counter()
        case_id, case = _build_case(request)
        yield _sse("ingest", {"case_id": case_id, "input_types": case.input_types})

        events: "queue.Queue[Optional[Tuple[str, Dict[str, Any]]]]" = queue.Queue()
        box: Dict[str, SafetyReport] = {}

        def worker() -> None:
            box["report"] = _run_pipeline(
                case_id,
                case,
                request.options.max_tool_calls,
                t0,
                on_event=lambda etype, payload: events.put((etype, payload)),
            )
            events.put(None)

        threading.Thread(target=worker, daemon=True).start()
        while True:
            item = events.get()
            if item is None:
                break
            yield _sse(*item)

        yield _sse("report", box["report"].model_dump())

    return StreamingResponse(gen(), media_type="text/event-stream")


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
