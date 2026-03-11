"""
API 数据模型 (Pydantic Schemas) v2.0

前后端之间的数据契约
v2.0: 支持多指标网格、影响半径参数
"""

from pydantic import BaseModel, Field


class StockPoint(BaseModel):
    """单只股票在 3D 空间中的表示"""

    code: str = Field(..., description="股票代码")
    name: str = Field(..., description="股票名称")
    x: float = Field(..., description="UMAP X 坐标")
    y: float = Field(..., description="UMAP Y 坐标")
    z: float = Field(..., description="Z 轴值 (当前活跃指标)")
    cluster_id: int = Field(0, description="聚类标签 (-1=噪声)")
    
    # v2.0: 所有指标的原始 Z 值
    z_pct_chg: float = Field(0, description="涨跌幅")
    z_turnover_rate: float = Field(0, description="换手率")
    z_volume: float = Field(0, description="成交量")
    z_amount: float = Field(0, description="成交额")
    z_pe_ttm: float = Field(0, description="市盈率(TTM)")
    z_pb: float = Field(0, description="市净率")


class ClusterInfo(BaseModel):
    """聚类簇信息"""

    cluster_id: int
    is_noise: bool = False
    size: int
    avg_probability: float
    top_stocks: list[str]
    stock_codes: list[str]
    feature_profile: dict[str, float] = {}


class TerrainBounds(BaseModel):
    """地形边界"""

    xmin: float
    xmax: float
    ymin: float
    ymax: float
    zmin: float = 0
    zmax: float = 1


class TerrainResponse(BaseModel):
    """地形数据完整响应 v2.0 — 包含所有指标的网格"""

    stocks: list[dict] = Field(default_factory=list, description="离散股票点")
    clusters: list[dict] = Field(default_factory=list, description="聚类摘要")
    
    # v2.0: 所有指标的地形网格
    grids: dict[str, list[float]] = Field(
        default_factory=dict,
        description="所有指标的扁平化高度网格 { metric: grid[] }"
    )
    bounds_per_metric: dict[str, dict] = Field(
        default_factory=dict,
        description="每个指标的 Z 轴范围 { metric: {zmin, zmax} }"
    )
    
    # 兼容 v1: 当前活跃指标的网格
    terrain_grid: list[float] = Field(
        default_factory=list, description="当前指标的扁平化高度网格 (row-major)"
    )
    terrain_resolution: int = Field(128, description="网格分辨率 N×N")
    bounds: dict = Field(default_factory=dict, description="空间边界")
    
    stock_count: int = 0
    cluster_count: int = 0
    computation_time_ms: float = 0
    active_metric: str = "pct_chg"


class HealthResponse(BaseModel):
    """健康检查响应"""

    status: str = "ok"
    data_sources: dict[str, bool] = {}
    stock_count: int = 0
    version: str = "2.0.0"


class ComputeRequest(BaseModel):
    """计算请求 v2.0"""

    z_metric: str = Field("pct_chg", description="Z 轴指标: pct_chg, turnover_rate, volume 等")
    features: list[str] | None = Field(
        None, description="聚类特征列表，为空则使用默认特征"
    )
    resolution: int = Field(128, ge=32, le=256, description="地形网格分辨率")
    radius_scale: float = Field(2.0, ge=0.5, le=8.0, description="影响半径缩放因子")


class StockSearchResult(BaseModel):
    """股票搜索结果"""

    code: str
    name: str
    price: float = 0
    pct_chg: float = 0
    x: float | None = None
    y: float | None = None
