from functools import lru_cache
from pathlib import Path
from typing import List, Sequence, Union

import yaml

from app.schemas.evidence import Signal
from app.schemas.tools import PatternMatchItem, PatternMatchResult


@lru_cache(maxsize=1)
def load_patterns() -> List[dict]:
    patterns_path = Path(__file__).resolve().parent.parent / "kb" / "patterns.yaml"
    if not patterns_path.exists():
        return []
    with open(patterns_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or []


def pattern_match(signals: Sequence[Union[str, Signal]]) -> PatternMatchResult:
    """Pure, deterministic set-matching of observed signals against YAML patterns.

    Contract:
    in: signals: list[str] (or list[Signal])
    out: PatternMatchResult with matched patterns, fired signals, and missing signals.
    """
    if not signals:
        return PatternMatchResult(matched_patterns=[], signals=[])

    # Convert input signals to a normalized set of string values
    input_signals = {
        (s.value if hasattr(s, "value") else str(s)).lower()
        for s in signals
    }

    patterns_def = load_patterns()
    matched: List[PatternMatchItem] = []

    for p in patterns_def:
        pid = p["id"]
        pname = p.get("name", pid)
        requires_all = [s.lower() for s in p.get("requires_all", [])]
        requires_any = [s.lower() for s in p.get("requires_any", [])]
        supporting = [s.lower() for s in p.get("supporting", [])]
        min_support = int(p.get("min_support", 0))
        advice_keys = p.get("advice_keys", [])

        # 1. Check requires_all
        if requires_all and not all(s in input_signals for s in requires_all):
            continue

        # 2. Check requires_any
        if requires_any and not any(s in input_signals for s in requires_any):
            continue

        # 3. Check supporting count
        supporting_fired = [s for s in supporting if s in input_signals]
        if len(supporting_fired) < min_support:
            continue

        # All declared signals in the pattern definition
        all_declared_signals: List[str] = []
        for s in requires_all + requires_any + supporting:
            if s not in all_declared_signals:
                all_declared_signals.append(s)

        fired = [s for s in all_declared_signals if s in input_signals]
        missing = [s for s in all_declared_signals if s not in input_signals]

        matched.append(
            PatternMatchItem(
                pattern_id=pid,
                name=pname,
                fired_signals=fired,
                missing_signals=missing,
                confidence=0.95,
                advice_keys=advice_keys,
            )
        )

    output_signals = [Signal.PATTERN_MATCH] if matched else []

    return PatternMatchResult(
        matched_patterns=matched,
        signals=output_signals,
    )
