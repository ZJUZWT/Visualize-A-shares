"""Decision quality helpers for AgentBrain."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any


WAIT_MARKERS = (
    "证据不足",
    "等待确认",
    "不要现在下单",
    "wait",
    "need confirmation",
)


@dataclass
class GateResult:
    accepted: list[dict[str, Any]]
    rejected: list[dict[str, Any]]
    requires_wait: bool
    assessment: dict[str, Any]
    self_critique: list[str]
    follow_up_questions: list[str]


def _empty_payload() -> dict[str, Any]:
    return {
        "assessment": {},
        "self_critique": [],
        "follow_up_questions": [],
        "decisions": [],
    }


def _strip_fenced_json(raw: str) -> str:
    text = raw.strip()
    if "```json" in text:
        return text.split("```json", 1)[1].split("```", 1)[0].strip()
    if text.startswith("```") and text.count("```") >= 2:
        return text.split("```", 2)[1].strip()
    return text


def _as_list_of_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str):
            item = item.strip()
            if item:
                result.append(item)
    return result


def build_system_prompt() -> str:
    return """你是一个经验丰富的 A 股投资经理型 Agent。

你的核心原则：
1. 关于信息，你的默认态度是怀疑。先问“谁在放这个消息？谁受益？”
2. Tier 1 证据优先：行情、成交、财报原文、交易所数据，高于研报观点和二手解读。
3. 不要因为单条消息改变策略。没有价格、仓位和风险纪律配合时，应保持克制。
4. 如果证据不足，请明确写出 self_critique 和 follow_up_questions，并输出空 decisions。
5. 只有当交易理由、止盈、止损、失效条件都足够明确时，才给出可执行动作。"""


def build_output_contract() -> str:
    return """请输出 JSON 对象，不要输出额外解释：
```json
{
  "assessment": {
    "market_posture": "bullish|bearish|neutral",
    "evidence_quality": "strong|mixed|weak"
  },
  "self_critique": ["..."],
  "follow_up_questions": ["..."],
  "decisions": [
    {
      "stock_code": "600519",
      "stock_name": "贵州茅台",
      "action": "buy|sell|add|reduce",
      "price": 1750.0,
      "quantity": 100,
      "holding_type": "long_term|mid_term|short_term",
      "reasoning": "...",
      "take_profit": 1820.0,
      "stop_loss": 1690.0,
      "risk_note": "...",
      "invalidation": "...",
      "confidence": 0.72
    }
  ]
}
```"""


def build_decision_context(
    *,
    analysis_results: list[dict[str, Any]],
    portfolio: dict[str, Any],
    config: dict[str, Any],
    memory_rules: list[dict[str, Any]],
    digests: list[dict[str, Any]],
    signal_hits: list[dict[str, Any]],
) -> str:
    positions = portfolio.get("positions", []) or []
    position_lines = []
    for position in positions:
        position_lines.append(
            f"- {position['stock_code']} {position.get('stock_name', '')}: "
            f"{position.get('current_qty', 0)}股, 成本{position.get('entry_price')}, 类型{position.get('holding_type')}"
        )
    if not position_lines:
        position_lines.append("（空仓）")

    analysis_lines = []
    for item in analysis_results:
        analysis_lines.append(f"### {item.get('stock_code', 'unknown')} {item.get('stock_name', '')}")
        analysis_lines.append(f"来源: {item.get('source', 'unknown')}")
        if "daily" in item:
            analysis_lines.append(f"行情: {item['daily']}")
        if "indicators" in item:
            analysis_lines.append(f"技术指标: {item['indicators']}")
        if "error" in item:
            analysis_lines.append(f"分析失败: {item['error']}")

    digest_lines = ["## 信息消化摘要"]
    if signal_hits:
        digest_lines.append("观察信号命中：")
        for hit in signal_hits:
            digest_lines.append(
                f"- {hit.get('stock_code', 'unknown')}: 关键词 [{','.join(hit.get('matched_keywords') or [])}]"
            )
    if digests:
        digest_lines.append("Digest：")
        for digest in digests:
            digest_lines.append(
                f"- {digest.get('stock_code', 'unknown')}: {digest.get('summary') or digest.get('strategy_relevance') or ''}"
            )
            digest_lines.append(f"  impact={digest.get('impact_assessment', 'none')}")
            evidence = digest.get("key_evidence") or []
            if evidence:
                digest_lines.append(f"  evidence={', '.join(str(item) for item in evidence)}")
    if len(digest_lines) == 1:
        digest_lines.append("暂无 digest 或命中信号。")

    memory_lines = ["## 历史经验"]
    if memory_rules:
        memory_lines.append("以下是你从过去交易中积累的经验规则，请在决策时参考：")
        for idx, rule in enumerate(memory_rules, start=1):
            confidence = float(rule.get("confidence") or 0.0)
            memory_lines.append(f"{idx}. {rule.get('rule_text', '')} (置信度: {confidence:.0%})")
    else:
        memory_lines.append("暂无已验证的经验规则。")

    single_pct = float(config.get("single_position_pct", 0.15))
    max_pos = int(config.get("max_position_count", 10))

    return f"""## 当前账户状态
- 现金余额：{float(portfolio.get('cash_balance') or 0.0):.2f}
- 总资产：{float(portfolio.get('total_asset') or 0.0):.2f}
- 当前持仓：
{chr(10).join(position_lines)}

## 候选标的分析
{chr(10).join(analysis_lines) if analysis_lines else '暂无候选分析'}

{chr(10).join(digest_lines)}

## 决策规则
1. 单只股票仓位不超过总资产的 {single_pct * 100:.0f}%
2. 同时持仓不超过 {max_pos} 只
3. quantity 必须是 100 的整数倍
4. 必须设置止盈和止损价格
5. 对已有持仓：检查是否需要止盈/止损/加仓/减仓
6. 今天日期: {date.today().isoformat()}

{chr(10).join(memory_lines)}
"""


def parse_decision_payload(raw: str) -> dict[str, Any]:
    text = _strip_fenced_json(raw)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return _empty_payload()

    if isinstance(parsed, list):
        payload = _empty_payload()
        payload["decisions"] = parsed
        return payload

    if not isinstance(parsed, dict):
        return _empty_payload()

    return {
        "assessment": parsed.get("assessment") if isinstance(parsed.get("assessment"), dict) else {},
        "self_critique": _as_list_of_strings(parsed.get("self_critique")),
        "follow_up_questions": _as_list_of_strings(parsed.get("follow_up_questions")),
        "decisions": parsed.get("decisions") if isinstance(parsed.get("decisions"), list) else [],
    }


def gate_decisions(payload: dict[str, Any], min_confidence: float = 0.65) -> GateResult:
    assessment = payload.get("assessment") if isinstance(payload.get("assessment"), dict) else {}
    self_critique = _as_list_of_strings(payload.get("self_critique"))
    follow_up_questions = _as_list_of_strings(payload.get("follow_up_questions"))
    decisions = payload.get("decisions") if isinstance(payload.get("decisions"), list) else []
    critique_text = " ".join(self_critique).lower()
    requires_wait = any(marker.lower() in critique_text for marker in WAIT_MARKERS)

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    if requires_wait:
        for index, decision in enumerate(decisions):
            rejected.append({
                "index": index,
                "reason": "self_critique_requires_wait",
                "decision": decision,
            })
        return GateResult(
            accepted=accepted,
            rejected=rejected,
            requires_wait=True,
            assessment=assessment,
            self_critique=self_critique,
            follow_up_questions=follow_up_questions,
        )

    for index, decision in enumerate(decisions):
        if not isinstance(decision, dict):
            rejected.append({"index": index, "reason": "invalid_decision_type", "decision": decision})
            continue
        if not decision.get("stock_code"):
            rejected.append({"index": index, "reason": "missing_stock_code", "decision": decision})
            continue
        if decision.get("stop_loss") in (None, ""):
            rejected.append({"index": index, "reason": "missing_stop_loss", "decision": decision})
            continue
        if decision.get("take_profit") in (None, ""):
            rejected.append({"index": index, "reason": "missing_take_profit", "decision": decision})
            continue
        try:
            confidence = float(decision.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence < min_confidence:
            rejected.append({"index": index, "reason": "low_confidence", "decision": decision})
            continue
        try:
            price = float(decision.get("price", 0.0))
            quantity = int(decision.get("quantity", 0))
        except (TypeError, ValueError):
            rejected.append({"index": index, "reason": "invalid_order_fields", "decision": decision})
            continue
        if price <= 0:
            rejected.append({"index": index, "reason": "invalid_price", "decision": decision})
            continue
        if quantity <= 0:
            rejected.append({"index": index, "reason": "invalid_quantity", "decision": decision})
            continue
        accepted.append(decision)

    return GateResult(
        accepted=accepted,
        rejected=rejected,
        requires_wait=False,
        assessment=assessment,
        self_critique=self_critique,
        follow_up_questions=follow_up_questions,
    )
