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
    n_neighbors: int = 30
    min_dist: float = 0.3
    n_components: int = 2
    metric: str = "euclidean"
    random_state: int = 42
    n_epochs: int = 500


class HDBSCANConfig(BaseModel):
    min_cluster_size: int = 20
    min_samples: int = 10
    metric: str = "euclidean"
    cluster_selection_method: str = "eom"  # Excess of Mass


class FeatureFusionConfig(BaseModel):
    """三层特征融合配置"""
    enabled: bool = True  # 是否启用融合（需要预计算数据）
    weight_industry: float = 3.0   # 行业 one-hot 权重
    weight_embedding: float = 2.0  # BGE 语义嵌入权重
    weight_numeric: float = 1.0    # 数值特征权重
    pca_target_dim: int = 50       # PCA 降维目标


class InterpolationConfig(BaseModel):
    method: str = "wendland_c2"
    grid_resolution: int = 128
    bounds_padding: float = 0.1
    radius_scale: float = 2.0        # 影响半径缩放因子
    k_neighbors: int = 5             # 自适应半径用的 K 近邻数
    min_radius: float = 0.3          # 最小影响半径
    max_radius: float = 5.0          # 最大影响半径


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


# ─── 聚合配置 ───────────────────────────────────────────
class AppConfig(BaseModel):
    datasource: DataSourceConfig = DataSourceConfig()
    umap: UMAPConfig = UMAPConfig()
    hdbscan: HDBSCANConfig = HDBSCANConfig()
    feature_fusion: FeatureFusionConfig = FeatureFusionConfig()
    interpolation: InterpolationConfig = InterpolationConfig()
    server: ServerConfig = ServerConfig()
    redis: RedisConfig = RedisConfig()


# 全局单例
settings = AppConfig()
