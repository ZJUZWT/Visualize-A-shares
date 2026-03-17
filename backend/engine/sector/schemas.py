"""板块研究仪表盘数据模型"""
from __future__ import annotations

from pydantic import BaseModel


class SectorBoardItem(BaseModel):
    """板块列表项"""
    board_code: str = ""
    board_name: str = ""
    board_type: str = ""  # 'industry' / 'concept'
    close: float = 0.0
    pct_chg: float = 0.0
    volume: float = 0.0
    amount: float = 0.0
    turnover_rate: float = 0.0
    total_mv: float = 0.0
    rise_count: int = 0
    fall_count: int = 0
    leading_stock: str = ""
    leading_pct_chg: float = 0.0
    # 资金流字段（可选，合并后填充）
    main_force_net_inflow: float | None = None
    main_force_net_ratio: float | None = None
    # 预测信号（可选）
    prediction_score: float | None = None
    prediction_signal: str | None = None  # 'bullish' / 'bearish' / 'neutral'


class SectorHistoryItem(BaseModel):
    """板块历史 K 线单条"""
    date: str
    open: float
    high: float
    low: float
    close: float
    pct_chg: float = 0.0
    volume: float = 0.0
    amount: float = 0.0
    turnover_rate: float = 0.0


class SectorFundFlowItem(BaseModel):
    """板块资金流向单条"""
    date: str = ""
    board_code: str = ""
    board_name: str = ""
    main_force_net_inflow: float = 0.0
    main_force_net_ratio: float = 0.0
    super_large_net_inflow: float = 0.0
    large_net_inflow: float = 0.0
    medium_net_inflow: float = 0.0
    small_net_inflow: float = 0.0


class ConstituentItem(BaseModel):
    """成分股"""
    code: str
    name: str = ""
    price: float = 0.0
    pct_chg: float = 0.0
    volume: float = 0.0
    amount: float = 0.0
    turnover_rate: float = 0.0
    pe_ttm: float | None = None
    pb: float | None = None


class SectorPredictionItem(BaseModel):
    """板块预测结果"""
    board_code: str = ""
    board_name: str = ""
    probability: float = 0.5
    signal: str = "neutral"  # 'bullish' / 'bearish' / 'neutral'
    factor_details: dict[str, float] = {}


class HeatmapCell(BaseModel):
    """热力图单元格"""
    board_code: str = ""
    board_name: str = ""
    pct_chg: float = 0.0
    main_force_net_inflow: float = 0.0
    main_force_net_ratio: float = 0.0


class RotationMatrixRow(BaseModel):
    """轮动矩阵一行（一个板块的多日资金流）"""
    board_code: str = ""
    board_name: str = ""
    daily_flows: list[float] = []
    daily_dates: list[str] = []
    trend_signal: str = "neutral"
    prediction: SectorPredictionItem | None = None


class SectorBoardsResponse(BaseModel):
    boards: list[SectorBoardItem] = []
    date: str = ""
    board_type: str = ""
    total: int = 0


class SectorHistoryResponse(BaseModel):
    board_code: str = ""
    board_name: str = ""
    history: list[SectorHistoryItem] = []
    fund_flow_history: list[SectorFundFlowItem] = []


class SectorHeatmapResponse(BaseModel):
    cells: list[HeatmapCell] = []
    date: str = ""
    board_type: str = ""


class SectorRotationResponse(BaseModel):
    matrix: list[RotationMatrixRow] = []
    days: int = 10
    board_type: str = ""
    top_bullish: list[SectorPredictionItem] = []
    top_bearish: list[SectorPredictionItem] = []


class SectorConstituentsResponse(BaseModel):
    board_code: str = ""
    board_name: str = ""
    constituents: list[ConstituentItem] = []
    total: int = 0
