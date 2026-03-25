from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DetectedEntities:
    stock_codes: list[str] = field(default_factory=list)
    stock_names: list[str] = field(default_factory=list)
    industries: list[str] = field(default_factory=list)
    intent_tags: list[str] = field(default_factory=list)


@dataclass
class PrefetchState:
    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    history: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    snapshot_excerpt: dict[str, dict[str, Any]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def has_stock_context(self) -> bool:
        return bool(self.profiles or self.history or self.snapshot_excerpt)


@dataclass
class ExecutionContext:
    message: str
    module: str
    history: list[dict] = field(default_factory=list)
    persona: str = "rag"
    entities: DetectedEntities = field(default_factory=DetectedEntities)
    prefetch: PrefetchState = field(default_factory=PrefetchState)
    signals: list[dict[str, Any]] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
