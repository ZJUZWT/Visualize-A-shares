# engine/rag/schemas.py
"""RAG 报告记录 Schema"""

from datetime import datetime
from pydantic import BaseModel


class ReportRecord(BaseModel):
    report_id: str          # 报告唯一 ID，格式: "{code}_{YYYYMMDDHHMMSS}"
    code: str               # 股票代码
    summary: str            # 完整分析摘要（向量化文本）
    signal: str | None      # "bullish" | "bearish" | "neutral" | None
    score: float | None     # -1.0 ~ 1.0，可为 None
    report_type: str        # "debate" | "agent_analysis"
    created_at: datetime
