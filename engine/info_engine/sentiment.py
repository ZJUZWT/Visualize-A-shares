# engine/info_engine/sentiment.py
"""情感分析器 — LLM 优先，规则退化"""

import json

from loguru import logger

from .schemas import SentimentResult

# ── 关键词词典 ──────────────────────────────────────────
POSITIVE_KEYWORDS = [
    "大增", "超预期", "增持", "回购", "中标", "突破", "创新高",
    "业绩预增", "扭亏", "净利润增长", "营收增长", "签约", "合作",
    "获批", "战略投资", "分红", "派息", "利好", "上调",
    "获得", "中标", "发明专利", "技术突破", "产能扩张",
    "并购", "重组成功", "解禁利好", "股权激励", "员工持股",
    "翻倍", "暴涨", "涨停", "新高", "强势", "爆发",
    "盈利", "景气", "高增长", "加速", "提升", "改善",
    "龙头", "行业第一", "市占率提升", "订单", "产销两旺",
]

NEGATIVE_KEYWORDS = [
    "减持", "亏损", "处罚", "退市", "暴雷", "违规", "下修",
    "破位", "跌停", "预亏", "业绩下滑", "净利润下降", "营收下降",
    "被调查", "立案", "警示", "ST", "造假", "诉讼", "仲裁",
    "解禁", "质押", "爆仓", "清仓", "减值", "商誉减值",
    "下调评级", "利空", "风险", "暴跌", "腰斩", "崩盘",
    "停产", "召回", "事故", "泄漏", "污染", "罚款",
    "终止", "失败", "流产", "取消", "延期", "推迟",
    "离职", "高管变动", "内斗", "举报", "实名举报",
]


class SentimentAnalyzer:
    """情感分析器 — LLM 优先，规则退化

    Args:
        llm_capability: LLMCapability 实例。None 或 disabled 时使用纯规则模式。
    """

    def __init__(self, llm_capability=None):
        self._llm = llm_capability

    async def analyze(self, title: str, content: str | None = None) -> SentimentResult:
        """分析新闻/公告的情感倾向"""
        if self._llm and self._llm.enabled:
            try:
                return await self._analyze_llm(title, content)
            except Exception as e:
                logger.warning(f"LLM 情感分析失败，退化为规则: {e}")
        return self._analyze_rules(title, content)

    def _analyze_rules(self, title: str, content: str | None) -> SentimentResult:
        """规则模式 — 关键词词典匹配"""
        text = title + ((" " + content) if content else "")

        pos_count = sum(1 for kw in POSITIVE_KEYWORDS if kw in text)
        neg_count = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text)

        total = pos_count + neg_count
        if total == 0:
            return SentimentResult(sentiment="neutral", score=0.0)

        score = (pos_count - neg_count) / total  # -1.0 ~ 1.0
        if score > 0.1:
            sentiment = "positive"
        elif score < -0.1:
            sentiment = "negative"
        else:
            sentiment = "neutral"

        return SentimentResult(sentiment=sentiment, score=round(score, 2))

    async def _analyze_llm(self, title: str, content: str | None) -> SentimentResult:
        """LLM 模式 — 调用 LLMCapability.classify()"""
        text = f"{title}\n{content or ''}"
        result = await self._llm.classify(
            text=text,
            categories=["positive", "negative", "neutral"],
            system="你是 A 股股票新闻情感分析专家。",
        )
        return SentimentResult(
            sentiment=result["label"],
            score=result.get("score", 0.0),
            reason=result.get("reason"),
        )
