"""Data hunger helpers for Main Agent wake/digest flow."""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any, Callable

from engine.agent.db import AgentDB
from engine.agent.service import AgentService


def _to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    return {"value": value}


def _listify(items: Any) -> list[dict[str, Any]]:
    if items is None:
        return []
    result = []
    for item in items:
        result.append(_to_dict(item))
    return result


def _join_text(item: dict[str, Any]) -> str:
    parts = [
        str(item.get("title") or ""),
        str(item.get("content") or ""),
        str(item.get("summary") or ""),
        str(item.get("type") or ""),
    ]
    return " ".join(part for part in parts if part).strip()


def _has_history_rows(daily_history: dict[str, Any]) -> bool:
    history = daily_history.get("history")
    return isinstance(history, list) and len(history) > 0


def _has_technical_signal(technical_indicators: dict[str, Any]) -> bool:
    return bool(technical_indicators)


def _build_immunity_assessment(
    *,
    triggers: list[dict[str, Any]],
    news_list: list[dict[str, Any]],
    announcement_list: list[dict[str, Any]],
    industry_context: dict[str, Any],
    daily_history: dict[str, Any],
    technical_indicators: dict[str, Any],
    missing_sources: list[str],
) -> dict[str, Any]:
    tier1_confirmed = []
    if announcement_list:
        tier1_confirmed.append("announcements")
    if _has_history_rows(daily_history):
        tier1_confirmed.append("daily_history")

    tier2_confirmed = []
    if industry_context:
        tier2_confirmed.append("industry_context")
    if _has_technical_signal(technical_indicators):
        tier2_confirmed.append("technical_indicators")

    tier3_confirmed = []
    if news_list:
        tier3_confirmed.append("news")
    if triggers:
        tier3_confirmed.append("watch_signals")

    missing_tier1_evidence = [
        name for name in ("announcements", "daily_history")
        if name not in tier1_confirmed
    ]
    for source in missing_sources:
        if source in {"announcements", "daily_history"} and source not in missing_tier1_evidence:
            missing_tier1_evidence.append(source)

    if len(tier1_confirmed) >= 2:
        evidence_tier = "tier1"
    elif tier1_confirmed and (tier2_confirmed or tier3_confirmed):
        evidence_tier = "mixed"
    elif tier2_confirmed:
        evidence_tier = "tier2"
    else:
        evidence_tier = "tier3"

    immunity_checks = [
        {
            "question": "这是否来自 Tier 1 证据？",
            "result": "pass" if tier1_confirmed else "fail",
            "detail": tier1_confirmed or ["none"],
        },
        {
            "question": "是否只是单条消息或情绪扰动？",
            "result": "warn" if news_list and not tier1_confirmed else "pass",
            "detail": ["news_only"] if news_list and not tier1_confirmed else ["not_news_only"],
        },
        {
            "question": "是否缺少能改策略的确认数据？",
            "result": "warn" if missing_tier1_evidence else "pass",
            "detail": missing_tier1_evidence or ["complete"],
        },
        {
            "question": "价格/走势是否提供辅助确认？",
            "result": "pass" if _has_history_rows(daily_history) or _has_technical_signal(technical_indicators) else "fail",
            "detail": ["confirmed"] if _has_history_rows(daily_history) or _has_technical_signal(technical_indicators) else ["missing"],
        },
        {
            "question": "行业上下文是否支持本次变化？",
            "result": "pass" if industry_context else "fail",
            "detail": [industry_context.get("cycle_position") or "missing"] if industry_context else ["missing"],
        },
        {
            "question": "结论是否需要先观察而不是立刻改策略？",
            "result": "pass" if missing_tier1_evidence or news_list else "pass",
            "detail": ["monitor_first" if (missing_tier1_evidence or news_list) else "actionable"],
        },
    ]

    if triggers and not missing_tier1_evidence and tier1_confirmed:
        suggested_action = "reassess"
    elif triggers or tier1_confirmed or tier2_confirmed or tier3_confirmed:
        suggested_action = "monitor"
    else:
        suggested_action = "ignore"

    strategy_change_bias = (
        "needs_tier1_confirmation"
        if missing_tier1_evidence
        else "eligible_for_reassessment"
        if suggested_action == "reassess"
        else "observe_only"
    )

    return {
        "evidence_tier": evidence_tier,
        "suggested_action": suggested_action,
        "strategy_change_bias": strategy_change_bias,
        "missing_tier1_evidence": missing_tier1_evidence,
        "immunity_checks": immunity_checks,
    }


class DataHungerService:
    """Fetches and digests multi-source evidence before final decisions."""

    def __init__(
        self,
        db: AgentDB,
        agent_service: AgentService,
        info_engine=None,
        industry_engine=None,
        daily_history_fetcher: Callable[[str], Any] | None = None,
        technical_indicator_fetcher: Callable[[str], Any] | None = None,
        llm_provider=None,
    ):
        self.db = db
        self.agent_service = agent_service
        self._info_engine = info_engine
        self._industry_engine = industry_engine
        self._daily_history_fetcher = daily_history_fetcher or self._default_daily_history_fetcher
        self._technical_indicator_fetcher = (
            technical_indicator_fetcher or self._default_technical_indicator_fetcher
        )
        self._llm = llm_provider

    async def query_industry_context(self, stock_code: str) -> dict[str, Any] | None:
        industry_engine = self._get_industry_engine()
        cognition_task = industry_engine.analyze(target=stock_code)
        capital_task = industry_engine.get_capital_structure(stock_code)
        cognition, capital = await asyncio.gather(cognition_task, capital_task, return_exceptions=True)

        cognition_dict = {} if isinstance(cognition, Exception) else _to_dict(cognition)
        capital_dict = {} if isinstance(capital, Exception) else _to_dict(capital)
        if not cognition_dict and not capital_dict:
            return None

        return {
            "industry": cognition_dict.get("industry"),
            "cycle_position": cognition_dict.get("cycle_position"),
            "key_drivers": cognition_dict.get("core_drivers") or cognition_dict.get("key_drivers") or [],
            "next_catalysts": cognition_dict.get("catalysts") or [],
            "risk_points": cognition_dict.get("risks") or [],
            "capital_summary": capital_dict.get("structure_summary") or "",
            "as_of_date": cognition_dict.get("as_of_date") or capital_dict.get("as_of_date") or "",
        }

    async def scan_watch_signals(self, portfolio_id: str) -> list[dict[str, Any]]:
        signals = await self.agent_service.list_watch_signals(portfolio_id, status="watching")
        info_engine = self._get_info_engine()
        hits: list[dict[str, Any]] = []

        for signal in signals:
            if signal.get("check_engine") != "info":
                continue
            stock_code = signal.get("stock_code")
            keywords = signal.get("keywords") or []
            if not stock_code or not keywords:
                continue

            news = _listify(await info_engine.get_news(stock_code, limit=20))
            announcements = _listify(await info_engine.get_announcements(stock_code, limit=10))
            evidence_pool = news + announcements
            matched = [
                keyword
                for keyword in keywords
                if any(keyword in _join_text(item) for item in evidence_pool)
            ]
            if not matched:
                continue

            hits.append(
                {
                    "signal_id": signal["id"],
                    "stock_code": stock_code,
                    "matched_keywords": matched,
                    "evidence": [
                        {
                            "title": item.get("title"),
                            "type": item.get("type") or "news",
                        }
                        for item in evidence_pool[:5]
                    ],
                    "signal": signal,
                }
            )

        return hits

    async def execute_and_digest(
        self,
        portfolio_id: str,
        run_id: str,
        stock_code: str,
        triggers: list[dict] | None = None,
    ) -> dict[str, Any]:
        triggers = triggers or []
        missing_sources: list[str] = []

        async def collect(name: str, awaitable):
            try:
                return await awaitable
            except Exception:
                missing_sources.append(name)
                return None

        news_task = collect("news", self._get_info_engine().get_news(stock_code, limit=20))
        announcements_task = collect(
            "announcements",
            self._get_info_engine().get_announcements(stock_code, limit=10),
        )
        industry_context_task = collect("industry_context", self.query_industry_context(stock_code))
        daily_history_task = collect("daily_history", self._run_fetcher(self._daily_history_fetcher, stock_code))
        technical_task = collect(
            "technical_indicators",
            self._run_fetcher(self._technical_indicator_fetcher, stock_code),
        )

        news, announcements, industry_context, daily_history, technical_indicators = await asyncio.gather(
            news_task,
            announcements_task,
            industry_context_task,
            daily_history_task,
            technical_task,
        )

        news_list = _listify(news)
        announcement_list = _listify(announcements)
        industry_context = industry_context or {}
        daily_history = _to_dict(daily_history)
        technical_indicators = _to_dict(technical_indicators)

        key_evidence: list[str] = []
        if triggers:
            key_evidence.append(f"watch signal hits: {len(triggers)}")
        if news_list:
            key_evidence.append(f"news_count={len(news_list)}")
        if announcement_list:
            key_evidence.append(f"announcement_count={len(announcement_list)}")
        if industry_context.get("cycle_position"):
            key_evidence.append(f"industry_cycle={industry_context['cycle_position']}")
        if technical_indicators:
            key_evidence.append("technical_indicators_available")

        risk_flags = list(industry_context.get("risk_points") or [])
        if missing_sources:
            risk_flags.append(f"missing_sources={','.join(missing_sources)}")
        immunity = _build_immunity_assessment(
            triggers=triggers,
            news_list=news_list,
            announcement_list=announcement_list,
            industry_context=industry_context,
            daily_history=daily_history,
            technical_indicators=technical_indicators,
            missing_sources=missing_sources,
        )

        impact_assessment = "none"
        if key_evidence:
            impact_assessment = "noted"
        if immunity["suggested_action"] == "monitor":
            impact_assessment = "minor_adjust"
        if immunity["suggested_action"] == "reassess":
            impact_assessment = "reassess"

        summary_parts = [
            f"标的 {stock_code}",
            f"news={len(news_list)}",
            f"announcements={len(announcement_list)}",
        ]
        if industry_context.get("industry"):
            summary_parts.append(f"industry={industry_context['industry']}")
        if industry_context.get("cycle_position"):
            summary_parts.append(f"cycle={industry_context['cycle_position']}")
        summary = " | ".join(summary_parts)

        watch_signal_updates = [
            {
                "signal_id": trigger["signal_id"],
                "matched_keywords": trigger.get("matched_keywords") or [],
            }
            for trigger in triggers
        ]
        strategy_relevance = (
            "watch signal triggered" if triggers
            else "monitor only" if key_evidence
            else "no actionable update"
        )

        raw_summary = {
            "news": news_list,
            "announcements": announcement_list,
            "daily_history": daily_history,
            "technical_indicators": technical_indicators,
            "triggers": triggers,
        }
        structured_summary = {
            "summary": summary,
            "key_evidence": key_evidence,
            "risk_flags": risk_flags,
            "watch_signal_updates": watch_signal_updates,
            "evidence_tier": immunity["evidence_tier"],
            "suggested_action": immunity["suggested_action"],
            "strategy_change_bias": immunity["strategy_change_bias"],
            "missing_tier1_evidence": immunity["missing_tier1_evidence"],
            "immunity_checks": immunity["immunity_checks"],
        }
        digest = await self.agent_service.create_info_digest(
            portfolio_id=portfolio_id,
            run_id=run_id,
            stock_code=stock_code,
            digest_type="wake",
            raw_summary=raw_summary,
            structured_summary=structured_summary,
            strategy_relevance=strategy_relevance,
            impact_assessment=impact_assessment,
            missing_sources=missing_sources,
        )
        return {
            **digest,
            "summary": summary,
            "key_evidence": key_evidence,
            "risk_flags": risk_flags,
            "industry_context": industry_context,
            "watch_signal_updates": watch_signal_updates,
            "evidence_tier": immunity["evidence_tier"],
            "suggested_action": immunity["suggested_action"],
            "strategy_change_bias": immunity["strategy_change_bias"],
            "missing_tier1_evidence": immunity["missing_tier1_evidence"],
            "immunity_checks": immunity["immunity_checks"],
        }

    def _get_info_engine(self):
        if self._info_engine is None:
            from engine.info import get_info_engine

            self._info_engine = get_info_engine()
        return self._info_engine

    def _get_industry_engine(self):
        if self._industry_engine is None:
            from engine.industry import get_industry_engine

            self._industry_engine = get_industry_engine()
        return self._industry_engine

    async def _run_fetcher(self, fetcher: Callable[[str], Any], stock_code: str):
        return await asyncio.to_thread(fetcher, stock_code)

    @staticmethod
    def _default_daily_history_fetcher(stock_code: str) -> dict[str, Any]:
        from engine.data import get_data_engine

        end = date.today()
        start = end - timedelta(days=60)
        df = get_data_engine().get_daily_history(stock_code, start.isoformat(), end.isoformat())
        if df is None or df.empty:
            return {"code": stock_code, "history": [], "total_days": 0}
        return {
            "code": stock_code,
            "history": df.tail(30).to_dict("records"),
            "total_days": len(df),
        }

    @staticmethod
    def _default_technical_indicator_fetcher(stock_code: str) -> dict[str, Any]:
        from engine.data import get_data_engine
        from engine.quant import get_quant_engine

        end = date.today()
        start = end - timedelta(days=90)
        daily_df = get_data_engine().get_daily_history(stock_code, start.isoformat(), end.isoformat())
        if daily_df is None or daily_df.empty:
            return {}
        return get_quant_engine().compute_indicators(daily_df)
