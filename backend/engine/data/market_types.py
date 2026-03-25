"""多市场统一资产类型定义。"""

from pydantic import BaseModel, Field


class AssetIdentity(BaseModel):
    market: str
    asset_type: str
    symbol: str
    display_name: str = ""
    currency: str = ""
    exchange: str = ""
    metadata: dict = Field(default_factory=dict)
