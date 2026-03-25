from __future__ import annotations

from .context import ExecutionContext


class ProgressiveEmitter:
    """统一构造渐进式 SSE 事件。"""

    @staticmethod
    def build_prefetch_ready(context: ExecutionContext) -> dict | None:
        if not context.prefetch.has_stock_context():
            return None
        return {
            "event": "prefetch_ready",
            "data": {
                "stock_codes": context.entities.stock_codes,
                "stock_names": context.entities.stock_names,
                "profile_count": len(context.prefetch.profiles),
                "history_count": len(context.prefetch.history),
            },
        }

    @staticmethod
    def build_early_insight(result: dict) -> dict | None:
        if not result.get("is_expert"):
            return None
        content = str(result.get("result", "")).strip()
        if not content:
            return None
        summary = content[:120].strip()
        return {
            "event": "early_insight",
            "data": {
                "engine": result.get("engine"),
                "action": result.get("action"),
                "summary": summary,
            },
        }
