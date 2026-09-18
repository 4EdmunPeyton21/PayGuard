from typing import Iterator, List, Optional, Tuple

from pydantic import BaseModel, Field

from app.schemas.evidence import Signal


class SignalItem(BaseModel):
    signal: Signal
    quote: str
    span: Tuple[int, int]
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)


class SignalScanResult(BaseModel):
    signals: List[SignalItem] = Field(default_factory=list)
    language: str = "en"
    has_link: bool = False

    def __iter__(self) -> Iterator[SignalItem]:
        return iter(self.signals)

    def __len__(self) -> int:
        return len(self.signals)

    def __getitem__(self, index: int) -> SignalItem:
        return self.signals[index]


class LookalikeCandidate(BaseModel):
    official: str
    distance: int
    kind: str


class UrlInspectResult(BaseModel):
    url: str
    scheme: str
    registered_domain: str
    subdomain: str
    tld: str
    path: str
    is_ip_host: bool
    is_punycode: bool
    is_shortener: bool
    hyphen_count: int
    subdomain_depth: int
    brand_token_outside_domain: List[str] = Field(default_factory=list)
    lookalike_candidates: List[LookalikeCandidate] = Field(default_factory=list)
    signals: List[Signal] = Field(default_factory=list)


class EntityDomainCheckResult(BaseModel):
    claimed_entity: str
    resolved_entity_id: Optional[str] = None
    entity_in_kb: bool
    official_domains: List[str] = Field(default_factory=list)
    match: bool
    matched_domain: Optional[str] = None
    unmatched_domains: List[str] = Field(default_factory=list)
    kb_ref: Optional[str] = None
    signals: List[Signal] = Field(default_factory=list)

    def __getitem__(self, item: str):
        return getattr(self, item)


class PatternMatchItem(BaseModel):
    pattern_id: str
    name: str
    fired_signals: List[str] = Field(default_factory=list)
    missing_signals: List[str] = Field(default_factory=list)
    confidence: float = 1.0
    advice_keys: List[str] = Field(default_factory=list)

    def __getitem__(self, item: str):
        return getattr(self, item)


class PatternMatchResult(BaseModel):
    matched_patterns: List[PatternMatchItem] = Field(default_factory=list)
    signals: List[Signal] = Field(default_factory=list)

    def __iter__(self):
        return iter(self.matched_patterns)

    def __len__(self) -> int:
        return len(self.matched_patterns)

    def __getitem__(self, item):
        if isinstance(item, int):
            return self.matched_patterns[item]
        return getattr(self, item)

    @property
    def patterns(self) -> List[PatternMatchItem]:
        return self.matched_patterns
