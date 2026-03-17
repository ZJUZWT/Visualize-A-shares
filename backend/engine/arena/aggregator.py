"""聚合逻辑 — 加权评分 + 冲突检测 + 信号判定"""

from datetime import datetime

from .schemas import AgentVerdict, AggregatedReport


# 信号阈值
BULLISH_THRESHOLD = 0.2
BEARISH_THRESHOLD = -0.2
CONFLICT_CONFIDENCE_THRESHOLD = 0.6


def aggregate_verdicts(
    target: str,
    verdicts: list[AgentVerdict],
    calibrations: dict[str, float],
) -> AggregatedReport:
    """聚合多个 Agent 的 Verdict 为统一报告

    加权公式: weighted_score[i] = score[i] * confidence[i] * calibration[i]
    overall_score = sum(weighted) / sum(confidence[i] * calibration[i])
    """
    if not verdicts:
        return AggregatedReport(
            target=target,
            overall_signal="neutral",
            overall_score=0.0,
            verdicts=[],
            conflicts=[],
            summary="无可用分析结果",
            risk_level="medium",
            timestamp=datetime.now(),
        )

    # 加权计算
    weighted_sum = 0.0
    weight_sum = 0.0
    for v in verdicts:
        cal = calibrations.get(v.agent_role, 0.5)
        w = v.confidence * cal
        weighted_sum += v.score * w
        weight_sum += w

    overall_score = weighted_sum / weight_sum if weight_sum > 0 else 0.0
    overall_score = max(-1.0, min(1.0, overall_score))

    # 信号判定
    if overall_score > BULLISH_THRESHOLD:
        overall_signal = "bullish"
    elif overall_score < BEARISH_THRESHOLD:
        overall_signal = "bearish"
    else:
        overall_signal = "neutral"

    # 冲突检测
    conflicts = []
    for i, v1 in enumerate(verdicts):
        for v2 in verdicts[i + 1:]:
            if (v1.signal != v2.signal
                and v1.signal != "neutral" and v2.signal != "neutral"
                and v1.confidence > CONFLICT_CONFIDENCE_THRESHOLD
                and v2.confidence > CONFLICT_CONFIDENCE_THRESHOLD):
                conflicts.append(
                    f"{v1.agent_role}({v1.signal}, {v1.confidence:.0%}) "
                    f"vs {v2.agent_role}({v2.signal}, {v2.confidence:.0%})"
                )

    # 风险等级
    abs_score = abs(overall_score)
    if abs_score > 0.6 and overall_signal == "bearish":
        risk_level = "high"
    elif conflicts or overall_signal == "bearish":
        risk_level = "medium"
    else:
        risk_level = "low"

    # 摘要
    agent_summaries = []
    for v in verdicts:
        agent_summaries.append(f"{v.agent_role}: {v.signal}({v.score:+.2f})")
    summary = f"综合评分 {overall_score:+.2f} ({overall_signal})。" + " | ".join(agent_summaries)
    if conflicts:
        summary += f" 注意: 存在 {len(conflicts)} 处多空分歧。"

    return AggregatedReport(
        target=target,
        overall_signal=overall_signal,
        overall_score=round(overall_score, 4),
        verdicts=verdicts,
        conflicts=conflicts,
        summary=summary,
        risk_level=risk_level,
        timestamp=datetime.now(),
    )
