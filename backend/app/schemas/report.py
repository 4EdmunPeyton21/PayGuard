from typing import List, Literal

from pydantic import BaseModel, Field

from app.schemas.evidence import Evidence


class ReportClaim(BaseModel):
    text: str
    evidence_ids: List[str] = Field(default_factory=list)


class SafetyReport(BaseModel):
    case_id: str
    risk_level: Literal["LOW_CONCERN", "CAUTION", "HIGH_RISK"]
    risk_score: float = 0.0
    headline: str
    why: List[ReportClaim] = Field(default_factory=list)
    evidence: List[Evidence] = Field(default_factory=list)
    recommended_actions: List[str] = Field(default_factory=list)
    unverified: List[str] = Field(default_factory=list)
    rules_fired: List[str] = Field(default_factory=list)
    policy_version: str = ""
    kb_version: str = ""
    model: str = "deterministic"
    tool_calls: int = 0
    latency_ms: int = 0
