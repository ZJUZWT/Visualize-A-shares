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


class ClusterAffinity(BaseModel):
    """簇隶属度（多归属关系）"""
    cluster_id: int = Field(..., description="簇 ID")
    affinity: float = Field(..., description="隶属度 (0~1)")


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

    # v7.0: 明日上涨概率
    z_rise_prob: float = Field(0.5, description="明日上涨概率 (0~1)")

    # v3.1: 同簇关联股票
    related_stocks: list[RelatedStock] = Field(
        default_factory=list, description="同簇相关股票(按距离排序)"
    )

    # v5.0: 多归属隶属度
    cluster_affinities: list[ClusterAffinity] = Field(
        default_factory=list, description="簇隶属度(top-k, 降序)"
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
    weight_embedding: float = Field(1.0, ge=0.0, le=5.0, description="嵌入权重")
    weight_industry: float = Field(0.0, ge=0.0, le=2.0, description="行业权重")
    weight_numeric: float = Field(0.0, ge=0.0, le=3.0, description="数值特征权重（0=不参与聚类）")
    pca_target_dim: int = Field(30, ge=10, le=100, description="最终 PCA 维度（仅高维时触发）")
    embedding_pca_dim: int = Field(15, ge=2, le=128, description="嵌入 UMAP 降维维度")


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


# ─── LLM Chat Schemas ─────────────────────────────────

class ChatRequest(BaseModel):
    """聊天请求"""
    message: str = Field(..., min_length=1, max_length=4096, description="用户消息")
    history: list[dict] = Field(
        default_factory=list,
        description='对话历史 [{"role": "user"|"assistant", "content": "..."}]'
    )

    # 上下文注入（前端自动填充当前地形数据）
    terrain_summary: dict | None = Field(None, description="地形概览数据")
    selected_stock: dict | None = Field(None, description="当前选中的股票")
    cluster_info: dict | None = Field(None, description="当前聚类信息")

    # 允许在请求级别覆盖 LLM 配置
    override_config: dict | None = Field(
        None,
        description="覆盖 LLM 配置 {provider, api_key, base_url, model, temperature, max_tokens}"
    )


class ChatResponse(BaseModel):
    """聊天同步响应"""
    content: str = Field(..., description="AI 回复内容")
    model: str = Field("", description="使用的模型")


class LLMConfigRequest(BaseModel):
    """LLM 配置更新请求"""
    provider: str | None = Field(None, description="openai_compatible | anthropic")
    api_key: str | None = Field(None, description="API Key")
    base_url: str | None = Field(None, description="API Base URL")
    model: str | None = Field(None, description="模型名称")
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(None, ge=64, le=32768)


class LLMConfigResponse(BaseModel):
    """LLM 配置状态响应"""
    enabled: bool = False
    provider: str = "openai_compatible"
    base_url: str = ""
    model: str = ""
    has_api_key: bool = False
    temperature: float = 0.7
    max_tokens: int = 2048
