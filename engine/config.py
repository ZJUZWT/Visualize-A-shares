"""
StockTerrain 全局配置
"""

from pathlib import Path
from pydantic import BaseModel

# ─── 路径 ───────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "stockterrain.duckdb"

DATA_DIR.mkdir(parents=True, exist_ok=True)


# ─── 数据源配置 ─────────────────────────────────────────
class DataSourceConfig(BaseModel):
    """三级数据源优先级与降级策略"""

    # AKShare: 主力数据源 (无需 API Key)
    akshare_enabled: bool = True

    # BaoStock: 备选数据源 (匿名可用)
    baostock_enabled: bool = True

    # Tushare Pro: 补充数据源 (需要 token)
    tushare_enabled: bool = False
    tushare_token: str = ""


# ─── 算法配置 ───────────────────────────────────────────
class UMAPConfig(BaseModel):
    n_neighbors: int = 25          # 降低: 更关注局部板块结构
    min_dist: float = 0.08         # 大幅降低: 让相似股票紧密聚拢，板块间留出间隔
    n_components: int = 2
    metric: str = "cosine"         # 改用余弦距离: 更适合归一化BGE嵌入
    random_state: int = 42
    n_epochs: int = 500


class HDBSCANConfig(BaseModel):
    min_cluster_size: int = 50     # 降低阈值: 允许30-50只的子行业独立成簇 (~25-30 个簇)
    min_samples: int = 3           # 降低核心点密度要求, 配合更小的 min_cluster_size
    metric: str = "euclidean"
    cluster_selection_method: str = "eom"  # EOM: 合并层次树中子簇，减少碎片化


class FeatureFusionConfig(BaseModel):
    """特征融合配置 v4.0 — UMAP 嵌入驱动聚类"""
    enabled: bool = True  # 是否启用融合（需要预计算数据）
    weight_industry: float = 0.0   # 行业 one-hot 权重（v4.0: 去掉）
    weight_embedding: float = 1.0  # BGE 语义嵌入权重（UMAP 降维后直接聚类）
    weight_numeric: float = 0.0    # 数值特征不参与聚类（保留用于画像和Z轴）
    pca_target_dim: int = 30       # 保留兼容性


class InterpolationConfig(BaseModel):
    method: str = "gaussian_kde"
    grid_resolution: int = 512
    bounds_padding: float = 0.1
    radius_scale: float = 2.0        # 影响半径缩放因子
    k_neighbors: int = 5             # 自适应半径用的 K 近邻数
    min_radius: float = 0.1          # 最小高斯带宽 σ
    max_radius: float = 5.0          # 最大高斯带宽 σ


# ─── 服务配置 ───────────────────────────────────────────
class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = True
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]


# ─── 缓存配置 ───────────────────────────────────────────
class RedisConfig(BaseModel):
    """Redis 可选 — 无 Redis 时退化为内存缓存"""

    enabled: bool = False
    host: str = "localhost"
    port: int = 6379
    db: int = 0


# ─── 量化引擎配置 ─────────────────────────────────────
class QuantConfig(BaseModel):
    """量化引擎配置"""
    icir_rolling_window: int = 20        # ICIR 滚动窗口天数
    auto_inject_on_startup: bool = True  # 启动时自动注入 ICIR 权重
    min_history_days: int = 5            # 自动校准最少需要的历史天数


# ─── ChromaDB 配置 ────────────────────────────────────
class ChromaDBConfig(BaseModel):
    """ChromaDB 嵌入式向量数据库配置"""
    persist_dir: str = str(DATA_DIR / "chromadb")
    retention_days: int = 90


# ─── 聚合配置 ───────────────────────────────────────────
class AppConfig(BaseModel):
    datasource: DataSourceConfig = DataSourceConfig()
    umap: UMAPConfig = UMAPConfig()
    hdbscan: HDBSCANConfig = HDBSCANConfig()
    feature_fusion: FeatureFusionConfig = FeatureFusionConfig()
    interpolation: InterpolationConfig = InterpolationConfig()
    server: ServerConfig = ServerConfig()
    redis: RedisConfig = RedisConfig()
    quant: QuantConfig = QuantConfig()
    chromadb: ChromaDBConfig = ChromaDBConfig()


# 全局单例
settings = AppConfig()
