from enum import StrEnum
from typing import Literal, Optional, Tuple

from pydantic import BaseModel, Field, model_validator


class Signal(StrEnum):
    # Urgency & Threat
    URGENCY_LANGUAGE = "urgency_language"
    THREAT_OF_CONSEQUENCE = "threat_of_consequence"

    # Requests
    CREDENTIAL_REQUEST = "credential_request"
    OTP_REQUEST = "otp_request"
    PIN_REQUEST = "pin_request"
    REMOTE_ACCESS_REQUEST = "remote_access_request"
    PAYMENT_REQUEST = "payment_request"

    # Social Engineering / Scam Promises
    UNSOLICITED_REFUND = "unsolicited_refund"
    INVESTMENT_PROMISE = "investment_promise"
    JOB_OFFER_FEE = "job_offer_fee"
    IMPERSONATION_CLAIM = "impersonation_claim"

    # Links & Technical Domain Signals
    EXTERNAL_LINK_PRESENT = "external_link_present"
    LINK_SHORTENER = "link_shortener"
    IP_ADDRESS_HOST = "ip_address_host"
    PUNYCODE_HOST = "punycode_host"
    LOOKALIKE_DOMAIN = "lookalike_domain"
    EXCESSIVE_SUBDOMAINS = "excessive_subdomains"
    DOMAIN_MISMATCH = "domain_mismatch"
    DOMAIN_VERIFIED_OFFICIAL = "domain_verified_official"
    UNKNOWN_ENTITY = "unknown_entity"
    BRAND_TOKEN_OUTSIDE_DOMAIN = "brand_token_outside_domain"

    # UPI Signals
    UPI_AMOUNT_MISMATCH = "upi_amount_mismatch"
    UPI_PAYEE_MISMATCH = "upi_payee_mismatch"
    UPI_COLLECT_REQUEST = "upi_collect_request"

    # Pattern & Meta Signals
    PATTERN_MATCH = "pattern_match"
    NO_ACTIONABLE_REQUEST = "no_actionable_request"
    SENDER_VERIFIED_CHANNEL = "sender_verified_channel"
    OCR_LOW_CONFIDENCE = "ocr_low_confidence"


class Evidence(BaseModel):
    id: str
    tool: str
    signal: Signal
    observed: str
    interpretation: str
    span: Optional[Tuple[int, int]] = None
    quote: Optional[str] = None
    direction: Literal["risk", "benign", "neutral"]
    strength: Literal["HIGH", "MEDIUM", "LOW"]
    confidence: float = Field(ge=0.0, le=1.0)
    kb_ref: Optional[str] = None

    @model_validator(mode="after")
    def validate_strength_grounding(self) -> "Evidence":
        if self.strength == "HIGH":
            has_quote = self.quote is not None and len(self.quote.strip()) > 0
            has_kb_ref = self.kb_ref is not None and len(self.kb_ref.strip()) > 0
            if not has_quote and not has_kb_ref:
                raise ValueError(
                    "A tool that cannot produce a quote or a kb_ref may not emit strength: HIGH."
                )
        return self


class EvidenceLedger(BaseModel):
    items: list[Evidence] = Field(default_factory=list)

    def add(self, evidence: Evidence) -> None:
        self.items.append(evidence)

    def get(self, evidence_id: str) -> Optional[Evidence]:
        for item in self.items:
            if item.id == evidence_id:
                return item
        return None

    def __iter__(self):
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, index: int) -> Evidence:
        return self.items[index]

    @property
    def signals(self) -> set[Signal]:
        return {item.signal for item in self.items}
