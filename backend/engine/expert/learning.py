"""Expert 学习画像聚合。"""

from __future__ import annotations

from typing import Any


def _clamp_score(value: float) -> int:
    return max(0, min(100, round(value)))


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _memory_focus_score(expert_type: str, memory: dict[str, Any]) -> tuple[int, float, int]:
    category = str(memory.get("category") or "").lower()
    text = str(memory.get("rule_text") or "")
    score = 0

    if expert_type == "data":
        if "data" in category or "估值" in text or "成交" in text or "量" in text:
            score += 6
    elif expert_type == "short_term":
        if "risk" in category or "追高" in text or "短线" in text or "止损" in text:
            score += 6
    elif expert_type == "quant":
        if "quant" in category or "信号" in text or "均线" in text or "突破" in text:
            score += 6
    elif expert_type == "info":
        if "info" in category or "消息" in text or "公告" in text or "催化" in text:
            score += 6
    elif expert_type == "industry":
        if "industry" in category or "行业" in text or "周期" in text or "产业链" in text:
            score += 6

    if "risk" in category:
        score += 2 if expert_type in {"rag", "short_term", "quant"} else 1
    if "data" in category:
        score += 2 if expert_type == "data" else 0

    return (
        score,
        _as_float(memory.get("confidence")),
        _as_int(memory.get("verify_count")),
    )


def build_expert_learning_profile(
    *,
    expert_type: str,
    portfolio_id: str,
    review_records: list[dict[str, Any]],
    plan_reviews: list[dict[str, Any]],
    review_stats: dict[str, Any],
    memories: list[dict[str, Any]],
    reflections: list[dict[str, Any]],
    pending_plan_count: int = 0,
) -> dict[str, Any]:
    """构建 Expert 页学习画像。"""
    total_reviews = _as_int(review_stats.get("total_reviews"))
    win_rate = _as_float(review_stats.get("win_rate"))
    avg_pnl_pct = _as_float(review_stats.get("avg_pnl_pct"))
    loss_count = _as_int(review_stats.get("loss_count"))
    plan_review_count = len(plan_reviews)
    plan_useful_count = sum(1 for item in plan_reviews if item.get("outcome_label") == "useful")
    plan_misleading_count = sum(1 for item in plan_reviews if item.get("outcome_label") == "misleading")

    active_memories = [item for item in memories if str(item.get("status") or "active") != "retired"]
    active_memories.sort(
        key=lambda item: _memory_focus_score(expert_type, item),
        reverse=True,
    )

    risk_memories = [
        item for item in active_memories
        if "risk" in str(item.get("category") or "").lower()
        or any(keyword in str(item.get("rule_text") or "") for keyword in ("止损", "回撤", "追高", "风险"))
    ]

    review_count = len(review_records) + plan_review_count
    memory_count = len(active_memories)
    reflection_count = len(reflections)
    verify_total = sum(_as_int(item.get("verify_count")) for item in active_memories)
    effective_win_rate = (
        (max(total_reviews - loss_count, 0) + plan_useful_count) / review_count
        if review_count
        else win_rate
    )
    effective_loss_count = loss_count + plan_misleading_count

    score_cards = [
        {
            "id": "decision_quality",
            "label": "决策质量",
            "score": _clamp_score(40 + effective_win_rate * 40 + avg_pnl_pct * 400 + plan_useful_count * 2),
            "summary": f"近 {review_count or total_reviews} 条复盘里，有效结论占比约 {round(effective_win_rate * 100, 1)}%。",
        },
        {
            "id": "risk_discipline",
            "label": "风控纪律",
            "score": _clamp_score(55 + (1 - (effective_loss_count / max(review_count, 1))) * 25 + len(risk_memories) * 4),
            "summary": f"负向复盘 {effective_loss_count} 条，已沉淀风控规则 {len(risk_memories)} 条。",
        },
        {
            "id": "review_depth",
            "label": "复盘沉淀度",
            "score": _clamp_score(30 + memory_count * 10 + verify_total * 2 + reflection_count * 8 + plan_review_count * 3),
            "summary": f"累计经验规则 {memory_count} 条，策略卡复盘 {plan_review_count} 条。",
        },
        {
            "id": "recent_stability",
            "label": "近期稳定度",
            "score": _clamp_score(35 + effective_win_rate * 35 + reflection_count * 8),
            "summary": f"近期反思 {reflection_count} 条，近期有效复盘占比 {round(effective_win_rate * 100, 1)}%。",
        },
        {
            "id": "boundary_clarity",
            "label": "适用边界清晰度",
            "score": _clamp_score(30 + len(risk_memories) * 12 + reflection_count * 6 + plan_misleading_count * 4),
            "summary": f"已形成边界/风险提示 {len(risk_memories)} 条，已证伪案例 {plan_misleading_count} 条。",
        },
    ]

    verified_knowledge = [
        {
            "id": item.get("id") or f"memory-{index}",
            "title": item.get("rule_text") or "已验证经验",
            "category": item.get("category") or "general",
            "confidence": _as_float(item.get("confidence")),
            "verify_count": _as_int(item.get("verify_count")),
        }
        for index, item in enumerate(active_memories[:5], start=1)
    ]

    recent_lessons = [
        {
            "id": item.get("id") or f"reflection-{index}",
            "date": item.get("date"),
            "title": item.get("summary") or "最近复盘结论",
            "category": item.get("category") or "reflection",
        }
        for index, item in enumerate(reflections, start=1)
        if item.get("summary")
    ]
    recent_lessons.extend(
        {
            "id": item.get("id") or f"plan-review-{index}",
            "date": item.get("review_date"),
            "title": item.get("lesson_summary") or item.get("summary") or "策略卡复盘结论",
            "category": f"plan_review:{item.get('outcome_label') or 'pending'}",
        }
        for index, item in enumerate(plan_reviews, start=1)
        if item.get("lesson_summary") or item.get("summary")
    )
    recent_lessons.sort(
        key=lambda item: str(item.get("date") or ""),
        reverse=True,
    )
    recent_lessons = recent_lessons[:4]

    common_mistakes = [
        {
            "id": item.get("id") or f"mistake-{index}",
            "title": item.get("summary") or "需要继续修正的动作",
        }
        for index, item in enumerate(reflections[:3], start=1)
        if item.get("summary")
    ]
    common_mistakes.extend(
        {
            "id": item.get("id") or f"plan-mistake-{index}",
            "title": item.get("lesson_summary") or item.get("summary") or "最近有一条策略卡需要继续修正。",
        }
        for index, item in enumerate(plan_reviews[:3], start=1)
        if item.get("outcome_label") == "misleading"
    )
    if not common_mistakes and loss_count > 0:
        common_mistakes.append({
            "id": "loss-review",
            "title": f"最近有 {loss_count} 条亏损复盘，说明执行节奏仍需修正。",
        })

    applicability_boundaries = [
        {
            "id": item.get("id") or f"boundary-{index}",
            "title": item.get("rule_text") or "边界待补充",
        }
        for index, item in enumerate(risk_memories[:4], start=1)
    ]

    return {
        "portfolio_id": portfolio_id,
        "expert_type": expert_type,
        "score_cards": score_cards,
        "verified_knowledge": verified_knowledge,
        "recent_lessons": recent_lessons,
        "common_mistakes": common_mistakes,
        "applicability_boundaries": applicability_boundaries,
        "source_summary": {
            "review_count": review_count,
            "memory_count": memory_count,
            "reflection_count": reflection_count,
            "win_rate": effective_win_rate,
        },
        "pending_plan_summary": {
            "expert_plan_count": pending_plan_count,
        },
    }
