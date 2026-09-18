"""PayGuard Risk Engine — deterministic, YAML-driven scoring.

Contract:
  in:  EvidenceLedger
  out: RiskResult with {level, score, rules_fired}

Every weight, threshold, gate, and FP guard lives in policy YAML.
Nothing is hardcoded here except the *mechanics* of how those
declarations are evaluated.
"""
from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Set

import yaml
from pydantic import BaseModel, Field

from app.schemas.evidence import EvidenceLedger

# ---- risk levels ----

class RiskLevel(StrEnum):
    LOW_CONCERN = "LOW_CONCERN"
    CAUTION = "CAUTION"
    HIGH_RISK = "HIGH_RISK"


LEVEL_ORDER: Dict[RiskLevel, int] = {
    RiskLevel.LOW_CONCERN: 0,
    RiskLevel.CAUTION: 1,
    RiskLevel.HIGH_RISK: 2,
}


# ---- result model ----

class RiskResult(BaseModel):
    level: RiskLevel
    score: int
    rules_fired: List[str] = Field(default_factory=list)
    policy_version: str = ""

    def __getitem__(self, item: str):
        return getattr(self, item)


# ---- policy loader ----

@lru_cache(maxsize=1)
def load_policy(policy_path: Optional[str] = None) -> dict:
    if policy_path is None:
        policy_path = str(
            Path(__file__).resolve().parent / "policy_v1.yaml"
        )
    path = Path(policy_path)
    if not path.exists():
        raise FileNotFoundError(f"Policy file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ---- helpers ----

def _signal_set(ledger: EvidenceLedger) -> Set[str]:
    return {e.signal.value for e in ledger.items}


def _check_gate(gate: dict, signals: Set[str]) -> bool:
    all_of = gate.get("all_of", [])
    any_of = gate.get("any_of", [])
    if all_of and not all(s in signals for s in all_of):
        return False
    if any_of and not any(s in signals for s in any_of):
        return False
    return True


def _check_fp_guard(guard: dict, signals: Set[str]) -> bool:
    all_of = guard.get("all_of", [])
    none_of = guard.get("none_of", [])
    if all_of and not all(s in signals for s in all_of):
        return False
    if none_of and any(s in signals for s in none_of):
        return False
    return True


# ---- engine ----

def evaluate(ledger: EvidenceLedger, policy_path: Optional[str] = None) -> RiskResult:
    policy = load_policy(policy_path)
    weights: Dict[str, int] = policy.get("weights", {})
    thresholds = policy.get("thresholds", {})
    gates: List[dict] = policy.get("gates", [])
    fp_guards: List[dict] = policy.get("fp_guards", [])
    evidence_floor = policy.get("evidence_floor", {})
    policy_version = policy.get("policy_version", "unknown")

    caution_threshold = int(thresholds.get("caution", 25))
    high_risk_threshold = int(thresholds.get("high_risk", 55))

    signals = _signal_set(ledger)
    rules_fired: List[str] = []

    # 1. Compute weighted score
    score = 0
    for sig in signals:
        w = weights.get(sig, 0)
        score += w
    score = max(score, 0)  # floor at 0

    # 2. Score-based level
    if score >= high_risk_threshold:
        level = RiskLevel.HIGH_RISK
        rules_fired.append(f"score:{score}>=threshold:{high_risk_threshold}")
    elif score >= caution_threshold:
        level = RiskLevel.CAUTION
        rules_fired.append(f"score:{score}>=threshold:{caution_threshold}")
    else:
        level = RiskLevel.LOW_CONCERN

    # 3. Gates — force HIGH_RISK regardless of score
    for gate in gates:
        if _check_gate(gate, signals):
            level = RiskLevel.HIGH_RISK
            rules_fired.append(f"gate:{gate['name']}")

    # 4. Evidence floor — prevent HIGH_RISK on thin evidence
    min_evidence = int(evidence_floor.get("high_risk_requires_min_evidence", 0))
    min_strength = evidence_floor.get("high_risk_requires_min_strength", None)

    if level == RiskLevel.HIGH_RISK and min_evidence > 0:
        risk_evidence = [e for e in ledger.items if e.direction == "risk"]
        if len(risk_evidence) < min_evidence:
            level = RiskLevel.CAUTION
            rules_fired.append(
                f"evidence_floor:risk_count={len(risk_evidence)}<{min_evidence}"
            )

    if level == RiskLevel.HIGH_RISK and min_strength:
        has_strong = any(
            e.strength == min_strength and e.direction == "risk"
            for e in ledger.items
        )
        if not has_strong:
            level = RiskLevel.CAUTION
            rules_fired.append(
                f"evidence_floor:no_{min_strength}_strength_evidence"
            )

    # 5. FP guards — cap level downward to protect legitimate messages
    for guard in fp_guards:
        if _check_fp_guard(guard, signals):
            cap_str = guard.get("cap", "CAUTION")
            cap_level = RiskLevel(cap_str)
            if LEVEL_ORDER.get(level, 0) > LEVEL_ORDER.get(cap_level, 0):
                level = cap_level
                rules_fired.append(f"fp_guard:{guard['name']}:cap={cap_str}")

    return RiskResult(
        level=level,
        score=score,
        rules_fired=rules_fired,
        policy_version=policy_version,
    )
