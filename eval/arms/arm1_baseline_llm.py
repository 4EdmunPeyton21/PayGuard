import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent.parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.config import settings
from app.llm.provider import get_model
from app.schemas.case import NormalisedCase
from app.schemas.report import ReportClaim, SafetyReport
from strands import Agent

# Naive baseline prompt - do NOT optimize or add few-shots
NAIVE_PROMPT = """You are a fraud and scam detection assistant.
Analyze the following incoming message and classify its risk level.

Message:
{text}

Respond ONLY with a JSON object in this format:
{{
  "level": "HIGH_RISK" | "CAUTION" | "LOW_CONCERN",
  "reasons": [
    "Reason 1 explaining why this is or is not suspicious",
    "Reason 2..."
  ]
}}
"""


def _clean_json_str(raw: str) -> str:
    cleaned = raw.strip()
    if "`json" in cleaned:
        cleaned = cleaned.split("`json", 1)[1].split("`", 1)[0].strip()
    elif "`" in cleaned:
        cleaned = cleaned.split("`", 1)[1].split("`", 1)[0].strip()
    return cleaned


def _parse_llm_json(raw: str) -> Dict[str, Any]:
    text = _clean_json_str(raw)
    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass

    # Heuristic fallback if formatting breaks
    upper = raw.upper()
    if "HIGH_RISK" in upper or "HIGH RISK" in upper:
        level = "HIGH_RISK"
    elif "LOW_CONCERN" in upper or "LOW RISK" in upper or "SAFE" in upper:
        level = "LOW_CONCERN"
    else:
        level = "CAUTION"

    return {"level": level, "reasons": [raw.strip()[:200]]}


def _normalize_level(raw_level: str) -> str:
    normalized = str(raw_level).upper().replace(" ", "_")
    if "HIGH" in normalized:
        return "HIGH_RISK"
    if "LOW" in normalized or "SAFE" in normalized or "BENIGN" in normalized:
        return "LOW_CONCERN"
    return "CAUTION"


def run_arm1(case: NormalisedCase) -> SafetyReport:
    """Contract: in: NormalisedCase -> out: SafetyReport (evidence list empty).

    Arm 1: The naive baseline LLM prompt.
    Takes message text, queries LLM with a single prompt, parses JSON output.
    Zero tools, zero grounding, zero evidence items.
    """
    start_time = time.perf_counter()
    model = get_model()
    agent = Agent(model=model, callback_handler=None)

    text_to_analyze = case.text or ""
    prompt = NAIVE_PROMPT.format(text=text_to_analyze)

    try:
        response = agent(prompt)
        raw_output = str(response)
        parsed = _parse_llm_json(raw_output)
    except Exception as exc:
        parsed = {
            "level": "CAUTION",
            "reasons": [f"LLM generation failed: {exc}"],
        }

    level = _normalize_level(parsed.get("level", "CAUTION"))
    reasons = parsed.get("reasons", [])
    if isinstance(reasons, str):
        reasons = [reasons]

    why_claims = [
        ReportClaim(text=str(r), evidence_ids=[])
        for r in reasons
    ]

    score_map = {"LOW_CONCERN": 10.0, "CAUTION": 40.0, "HIGH_RISK": 85.0}
    latency_ms = int((time.perf_counter() - start_time) * 1000)

    return SafetyReport(
        case_id=case.case_id,
        risk_level=level,  # type: ignore[arg-type]
        risk_score=score_map.get(level, 40.0),
        headline=f"Naive LLM baseline assessment: {level}",
        why=why_claims,
        evidence=[],  # Evidence list strictly empty per contract
        recommended_actions=[],
        unverified=["Unverified: LLM output without tool grounding or evidence"],
        model=settings.llm_model,
        tool_calls=0,
        latency_ms=latency_ms,
    )
