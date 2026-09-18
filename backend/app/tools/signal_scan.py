import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Tuple

import yaml

from app.schemas.evidence import Signal
from app.schemas.tools import SignalItem, SignalScanResult


@lru_cache(maxsize=1)
def _load_lexicon() -> Dict[str, dict]:
    lexicon_path = Path(__file__).resolve().parent.parent / "kb" / "lexicon.yaml"
    if not lexicon_path.exists():
        return {}
    with open(lexicon_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def detect_language(text: str) -> str:
    # Check for Devanagari script
    if re.search(r"[\u0900-\u097F]", text):
        return "hi"
    # Check for common Hinglish markers
    hinglish_markers = ["ho jayega", "karein", "jaldi", "turant", "band ho"]
    text_lower = text.lower()
    if any(marker in text_lower for marker in hinglish_markers):
        return "hi-Latn"
    return "en"


def signal_scan(text: str) -> SignalScanResult:
    """Pure, deterministic scan of text against the YAML lexicon.

    Returns detected SignalItems with character spans, grounded quotes,
    and confidence scores.
    """
    if not text:
        return SignalScanResult(signals=[], language="en", has_link=False)

    lexicon = _load_lexicon()
    has_link = bool(re.search(r"https?://\S+", text))
    language = detect_language(text)

    detected_signals: List[SignalItem] = []

    # Risk signals to evaluate
    risk_signal_keys = [
        ("urgency_language", Signal.URGENCY_LANGUAGE),
        ("threat_of_consequence", Signal.THREAT_OF_CONSEQUENCE),
        ("credential_request", Signal.CREDENTIAL_REQUEST),
    ]

    for key, signal_enum in risk_signal_keys:
        cfg = lexicon.get(key, {})
        patterns = cfg.get("patterns", [])
        confidence = float(cfg.get("confidence", 0.9))

        matches: List[Tuple[int, int, str]] = []
        for pat in patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                start, end = m.span()
                matches.append((start, end, text[start:end]))

        if matches:
            # Pick the longest match for this signal
            matches.sort(key=lambda x: (x[1] - x[0]), reverse=True)
            start, end, quote = matches[0]
            detected_signals.append(
                SignalItem(
                    signal=signal_enum,
                    quote=quote,
                    span=(start, end),
                    confidence=confidence,
                )
            )

    # If no risk signals fired, check for benign / informational transactions
    if not detected_signals:
        info_cfg = lexicon.get("informational_transaction", {})
        patterns = info_cfg.get("patterns", [])
        confidence = float(info_cfg.get("confidence", 0.95))

        matches = []
        for pat in patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                start, end = m.span()
                matches.append((start, end, text[start:end]))

        if matches:
            matches.sort(key=lambda x: (x[1] - x[0]), reverse=True)
            start, end, quote = matches[0]
            detected_signals.append(
                SignalItem(
                    signal=Signal.NO_ACTIONABLE_REQUEST,
                    quote=quote,
                    span=(start, end),
                    confidence=confidence,
                )
            )

    return SignalScanResult(
        signals=detected_signals,
        language=language,
        has_link=has_link,
    )
