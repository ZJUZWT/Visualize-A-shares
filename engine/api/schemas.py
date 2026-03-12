"""
API 数据模型 (Pydantic Schemas) v2.0

前后端之间的数据契约
v2.0: 支持多指标网格、影响半径参数
"""

from pydantic import BaseModel, Field


class RelatedStock(BaseModel):
    """同簇相关股票"""
    code: str
    name: str
    industry: str = ""
    pct_chg: float = 0.0


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

    # v3.1: 同簇关联股票
    related_stocks: list[RelatedStock] = Field(
        default_factory=list, description="同簇相关股票(按距离排序)"
    )


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
    """计算请求 v3.0 — 支持聚类权重调节"""

    z_metric: str = Field("pct_chg", description="Z 轴指标: pct_chg, turnover_rate, volume 等")
    features: list[str] | None = Field(
        None, description="聚类特征列表，为空则使用默认特征"
    )
    resolution: int = Field(512, ge=32, le=1024, description="地形网格分辨率")
    radius_scale: float = Field(2.0, ge=0.1, le=8.0, description="影响半径缩放因子")

    # v4.0: 聚类权重参数（默认值与 features.py 同步）
    weight_embedding: float = Field(2.0, ge=0.0, le=5.0, description="嵌入权重")
    weight_industry: float = Field(0.0, ge=0.0, le=2.0, description="行业权重")
    weight_numeric: float = Field(0.5, ge=0.0, le=3.0, description="数值权重")
    pca_target_dim: int = Field(50, ge=10, le=100, description="PCA 维度")
    embedding_pca_dim: int = Field(50, ge=8, le=128, description="嵌入 PCA 维度")


class StockSearchResult(BaseModel):
    """股票搜索结果"""

    code: str
    name: str
    price: float = 0
    pct_chg: float = 0
    x: float | None = None
    y: float | None = None


class HistoryRequest(BaseModel):
    """历史回放请求"""
    days: int = Field(7, ge=2, le=30, description="回溯天数（交易日）")
    z_metric: str = Field("pct_chg", description="Z 轴指标")


class HistoryFrame(BaseModel):
    """单帧历史数据"""
    date: str
    terrain_grid: list[float]
    bounds: dict
    stock_z_values: dict[str, float]


class HistoryResponse(BaseModel):
    """历史回放响应"""
    frames: list[HistoryFrame]
    dates: list[str]
    total_stocks: int = 0
