"""Citation enforcement for PayGuard narrator output.

Validates that every evidence_id referenced in a narration actually exists
in the evidence ledger.  A phantom evidence ID (e.g. "E99") that doesn't
exist in the ledger indicates hallucination and triggers a rejection.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from app.schemas.evidence import EvidenceLedger
from app.schemas.report import ReportClaim


@dataclass
class CitationError:
    claim_text: str
    phantom_ids: List[str]

    def __str__(self) -> str:
        ids = ", ".join(self.phantom_ids)
        return f"Claim cites nonexistent evidence IDs [{ids}]: {self.claim_text[:80]}"


@dataclass
class CitationResult:
    ok: bool
    errors: List[CitationError] = field(default_factory=list)

    def __str__(self) -> str:
        if self.ok:
            return "CitationResult: OK"
        msgs = "; ".join(str(e) for e in self.errors)
        return f"CitationResult: FAILED — {msgs}"


def check_citations(
    claims: List[ReportClaim],
    ledger: EvidenceLedger,
) -> CitationResult:
    """Verify that every evidence_id in every claim exists in the ledger.

    Returns CitationResult(ok=True) if all citations resolve.
    Returns CitationResult(ok=False, errors=[...]) if any phantom IDs found.
    """
    valid_ids = {e.id for e in ledger.items}
    errors: List[CitationError] = []

    for claim in claims:
        phantoms = [eid for eid in claim.evidence_ids if eid not in valid_ids]
        if phantoms:
            errors.append(CitationError(claim_text=claim.text, phantom_ids=phantoms))

    return CitationResult(ok=len(errors) == 0, errors=errors)
