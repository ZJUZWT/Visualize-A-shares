"""数据引擎 Pydantic 响应模型"""

from pydantic import BaseModel, Field


class DataHealthResponse(BaseModel):
    status: str = "ok"
    data_sources: dict[str, bool] = Field(default_factory=dict)
    stock_count: int = 0
    profiles_count: int = 0


class ProfileResponse(BaseModel):
    code: str
    name: str = ""
    industry: str = ""
    scope: str = ""


class SnapshotStockResponse(BaseModel):
    code: str
    name: str = ""
    price: float = 0.0
    pct_chg: float = 0.0
    volume: int = 0
    amount: float = 0.0
    turnover_rate: float = 0.0
    pe_ttm: float = 0.0
    pb: float = 0.0
