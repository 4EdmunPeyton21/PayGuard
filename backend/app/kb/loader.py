import hashlib
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pydantic import BaseModel, Field


class Entity(BaseModel):
    id: str
    name: str
    aliases: List[str] = Field(default_factory=list)
    official_domains: List[str] = Field(default_factory=list)
    official_sms_senders: List[str] = Field(default_factory=list)
    sector: str
    never_asks_for: List[str] = Field(default_factory=list)
    source: str = ""
    version: int = 1


class KnowledgeBase:
    def __init__(self, kb_dir: Optional[Path | str] = None):
        if kb_dir is not None:
            self.kb_dir = Path(kb_dir)
        else:
            self.kb_dir = Path(__file__).resolve().parent

        self.entities: Dict[str, Entity] = {}
        self._alias_index: Dict[str, str] = {}
        self._version: str = "kb@uninitialized"
        self.load()

    def load(self) -> None:
        entities_file = self.kb_dir / "entities.yaml"
        if not entities_file.exists():
            return

        content_bytes = entities_file.read_bytes()
        content_hash = hashlib.sha256(content_bytes).hexdigest()[:8]
        self._version = f"kb@{content_hash}"

        raw_data = yaml.safe_load(content_bytes.decode("utf-8")) or []
        self.entities.clear()
        self._alias_index.clear()

        for item in raw_data:
            entity = Entity(**item)
            self.entities[entity.id] = entity

            # Index by normalized ID
            self._alias_index[entity.id.lower()] = entity.id

            # Index by normalized Name
            self._alias_index[entity.name.strip().lower()] = entity.id

            # Index by all aliases
            for alias in entity.aliases:
                self._alias_index[alias.strip().lower()] = entity.id

    @property
    def version(self) -> str:
        return self._version

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        return self.entities.get(entity_id)

    def resolve_entity(self, query: Optional[str]) -> Optional[Entity]:
        if not query or not query.strip():
            return None

        normalized = query.strip().lower()

        # Direct match in alias index
        if normalized in self._alias_index:
            entity_id = self._alias_index[normalized]
            return self.entities.get(entity_id)

        # Try stripped of common punctuation (e.g. periods)
        cleaned = normalized.replace(".", "").strip()
        if cleaned in self._alias_index:
            entity_id = self._alias_index[cleaned]
            return self.entities.get(entity_id)

        # Strip common entity suffixes (e.g. "SBI Bank" -> "SBI")
        suffixes = [
            " bank ltd",
            " bank limited",
            " pvt ltd",
            " ltd",
            " limited",
            " bank",
            " support",
            " care",
            " customer care",
        ]
        for suffix in suffixes:
            if cleaned.endswith(suffix):
                stem = cleaned[: -len(suffix)].strip()
                if stem in self._alias_index:
                    entity_id = self._alias_index[stem]
                    return self.entities.get(entity_id)

        # Check if any known alias (length >= 3) appears as a whole word in query
        import re

        for alias, eid in sorted(
            self._alias_index.items(), key=lambda x: len(x[0]), reverse=True
        ):
            if len(alias) >= 3 and re.search(
                r"\b" + re.escape(alias) + r"\b", cleaned
            ):
                return self.entities.get(eid)

        return None


# Default shared instance
kb = KnowledgeBase()
