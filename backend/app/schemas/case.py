from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class NormalisedCase(BaseModel):
    case_id: str
    input_types: List[Literal["text", "url", "screenshot", "qr"]]
    text: Optional[str] = None
    text_source: Optional[Literal["user", "ocr"]] = None
    ocr_confidence: Optional[float] = None
    urls: List[str] = Field(default_factory=list)
    qr_payloads: List[str] = Field(default_factory=list)
    payment_context: Optional[str] = None
    image_ref: Optional[str] = None


class AnalyzeOptions(BaseModel):
    max_tool_calls: int = 6
    arm: str = "agent_tools"


class AnalyzeRequest(BaseModel):
    text: Optional[str] = None
    payment_context: Optional[str] = None
    image_ref: Optional[str] = None
    options: AnalyzeOptions = Field(default_factory=AnalyzeOptions)
