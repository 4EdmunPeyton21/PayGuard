"""Certainty lint for PayGuard narrator output.

A regex pass over the headline and claim texts to catch banned absolute-
certainty phrases.  The narrator must use hedged language ("indicates",
"consistent with", "could not be verified") rather than absolute claims
("this is definitely a scam", "certainly fraudulent", etc.).

Banned phrases come from the PDF spec section 6 narrator hard rules:
  "definitely", "certainly", "this is a scam", "fraudulent",
  "guaranteed", "100%"

And the variants the spec explicitly warns about:
  "this is definitely a scam", "definitely a scam", "certainly fraud",
  etc.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

# ---------------------------------------------------------------------------
# Banned phrase patterns (case-insensitive)
# Each entry is (pattern_str, readable_name).
# ---------------------------------------------------------------------------
_BANNED: List[tuple[str, str]] = [
    (r"\bdefinitely\b", "definitely"),
    (r"\bcertainly\b", "certainly"),
    (r"\bguaranteed\b", "guaranteed"),
    (r"\b100\s*%\b", "100%"),
    (r"\bfraudulent\b", "fraudulent"),
    (r"\bthis\s+is\s+a\s+scam\b", "this is a scam"),
    (r"\bthis\s+is\s+definitely\b", "this is definitely"),
    (r"\bis\s+definitely\s+a\s+scam\b", "is definitely a scam"),
    (r"\bthis\s+is\s+fraud\b", "this is fraud"),
    (r"\bis\s+a\s+fraudster\b", "is a fraudster"),
    (r"\bproven\s+scam\b", "proven scam"),
    (r"\bconfirmed\s+(scam|fraud)\b", "confirmed scam/fraud"),
    (r"\bwithout\s+doubt\b", "without doubt"),
    (r"\bno\s+doubt\b", "no doubt"),
]

_COMPILED = [(re.compile(pat, re.IGNORECASE), name) for pat, name in _BANNED]


@dataclass
class LintViolation:
    text: str
    matched_phrase: str

    def __str__(self) -> str:
        return (
            f"Banned phrase '{self.matched_phrase}' found in: "
            f"{self.text[:80]!r}"
        )


@dataclass
class LintResult:
    ok: bool
    violations: List[LintViolation] = field(default_factory=list)

    def __str__(self) -> str:
        if self.ok:
            return "LintResult: OK"
        msgs = "; ".join(str(v) for v in self.violations)
        return f"LintResult: FAILED — {msgs}"


def lint_narration(
    headline: str,
    claims: List[str],
) -> LintResult:
    """Run the banned-phrase regex pass over headline + all claim texts.

    Returns LintResult(ok=True) if no violations.
    Returns LintResult(ok=False, violations=[...]) if any banned phrase found.
    """
    texts = [headline] + list(claims)
    violations: List[LintViolation] = []

    for text in texts:
        for pattern, name in _COMPILED:
            if pattern.search(text):
                violations.append(LintViolation(text=text, matched_phrase=name))
                break  # one violation per text block is enough

    return LintResult(ok=len(violations) == 0, violations=violations)
