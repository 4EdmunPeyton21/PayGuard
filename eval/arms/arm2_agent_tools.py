"""D17: Arm 2 -- the actual system under test.

Contract: in: NormalisedCase -> out: SafetyReport.

Adaptive agent loop (D14, investigate()) -> deterministic risk engine (D9)
-> validated narrator with citation/lint checks and template fallback
(D16). This is the same pipeline main.py's /api/v1/analyze runs, minus
DynamoDB persistence -- an eval arm is a pure function over a case.
"""
import sys
import time
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.agent.investigator import investigate  # noqa: E402
from app.agent.narrator import get_recommended_actions, narrate  # noqa: E402
from app.kb.loader import kb  # noqa: E402
from app.risk.engine import evaluate_ledger  # noqa: E402
from app.schemas.case import NormalisedCase  # noqa: E402
from app.schemas.evidence import Signal  # noqa: E402
from app.schemas.report import SafetyReport  # noqa: E402


def run_arm2(case: NormalisedCase, max_tool_calls: int = 6) -> SafetyReport:
    start_time = time.perf_counter()

    inv_result = investigate(case, max_tool_calls=max_tool_calls)
    risk_res = evaluate_ledger(inv_result.ledger)

    claimed_entity = None
    for e in inv_result.ledger.items:
        if e.signal == Signal.IMPERSONATION_CLAIM and e.quote:
            claimed_entity = e.quote
            break

    narration = narrate(
        ledger=inv_result.ledger,
        level=risk_res.level.value,
        claimed_entity=claimed_entity,
    )

    signals = [e.signal for e in inv_result.ledger.items]
    actions = get_recommended_actions(signals)
    latency_ms = int((time.perf_counter() - start_time) * 1000)

    return SafetyReport(
        case_id=case.case_id,
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
