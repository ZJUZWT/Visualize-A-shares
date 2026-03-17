"""产业链引擎数据结构"""

from typing import Literal

from pydantic import BaseModel, Field


class IndustryCognition(BaseModel):
    """行业产业链认知 — LLM 生成，缓存复用

    NOTE: 从 agent/schemas.py 迁移至此，成为 IndustryEngine 的核心输出。
    agent/schemas.py 中通过 re-export 保持兼容。
    """
    industry: str                    # 行业名称（如"小金属"、"半导体"）
    target: str                      # 触发股票代码

    # 产业链结构
    upstream: list[str] = Field(default_factory=list)
    downstream: list[str] = Field(default_factory=list)
    core_drivers: list[str] = Field(default_factory=list)
    cost_structure: str = ""
    barriers: str = ""

    # 供需格局
    supply_demand: str = ""

    # 认知陷阱
    common_traps: list[str] = Field(default_factory=list)

    # 周期定位
    cycle_position: str = ""         # 景气上行|下行|拐点向上|拐点向下|高位震荡|底部盘整
    cycle_reasoning: str = ""

    # 催化剂/风险
    catalysts: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)

    # 元数据
    generated_at: str = ""
    as_of_date: str = ""


class IndustryMapping(BaseModel):
    """行业→股票映射"""
    industry: str
    stocks: list[str]               # 股票代码列表
    stock_count: int = 0


class IndustryAnalysisRequest(BaseModel):
    """产业链分析请求"""
    target: str = Field(description="股票代码如 '600519'，或行业名如 '半导体'")
    target_type: Literal["stock", "industry"] = "stock"
    as_of_date: str = ""            # 空字符串时 fallback 到 today


class CapitalStructure(BaseModel):
    """资金构成分析 — 黑板公共知识"""
    code: str
    as_of_date: str = ""

    # 主力资金
    main_force_net_inflow: str = ""       # 主力净流入
    main_force_ratio: str = ""            # 主力净流入占比
    super_large_net_inflow: str = ""      # 超大单净流入
    large_net_inflow: str = ""            # 大单净流入
    small_net_inflow: str = ""            # 小单净流入

    # 北向持股
    northbound_shares: str = ""           # 持股数量
    northbound_market_value: str = ""     # 持股市值
    northbound_ratio: str = ""            # 持股占比
    northbound_change: str = ""           # 持股变化

    # 融资融券
    margin_balance: str = ""              # 融资余额
    margin_buy: str = ""                  # 融资买入额
    short_selling_volume: str = ""        # 融券余量

    # 换手率
    turnover_rate: float = 0.0

    # 综合判断
    structure_summary: str = ""           # 资金构成摘要
