"""
StockScape 全局配置
"""

import os
from pathlib import Path
from pydantic import BaseModel

# ─── 路径 ───────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "stockterrain.duckdb"
AGENT_DB_LEGACY_PATH = DATA_DIR / "agent.duckdb"
AGENT_DB_PATH = DATA_DIR / "main_agent.duckdb"

DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_env_file() -> None:
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.lower() in ("1", "true", "yes", "on")


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


_load_env_file()


# ─── 数据源配置 ─────────────────────────────────────────
class DataSourceConfig(BaseModel):
    """三级数据源优先级与降级策略"""

    # AKShare: 主力数据源 (无需 API Key)
    akshare_enabled: bool = _env_bool("AKSHARE_ENABLED", True)

    # BaoStock: 备选数据源 (匿名可用)
    baostock_enabled: bool = _env_bool("BAOSTOCK_ENABLED", True)

    # Tushare Pro: 补充数据源 (需要 token)
    tushare_enabled: bool = _env_bool("TUSHARE_ENABLED", False)
    tushare_token: str = _env_str("TUSHARE_TOKEN", "")

    # 盘中快照自动刷新间隔（分钟），交易时段内快照超过此时间自动重新拉取
    snapshot_refresh_minutes: int = _env_int("SNAPSHOT_REFRESH_MINUTES", 30)


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
    host: str = _env_str("SERVER_HOST", "0.0.0.0")
    port: int = _env_int("SERVER_PORT", 8000)
    reload: bool = _env_bool("SERVER_RELOAD", True)
    cors_origins: list[str] = _env_list(
        "CORS_ORIGINS",
        [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
    )


# ─── 缓存配置 ───────────────────────────────────────────
class RedisConfig(BaseModel):
    """Redis 可选 — 无 Redis 时退化为内存缓存"""

    enabled: bool = _env_bool("REDIS_ENABLED", False)
    host: str = _env_str("REDIS_HOST", "localhost")
    port: int = _env_int("REDIS_PORT", 6379)
    db: int = _env_int("REDIS_DB", 0)


# ─── 量化引擎配置 ─────────────────────────────────────
class QuantConfig(BaseModel):
    """量化引擎配置"""
    icir_rolling_window: int = _env_int("QUANT_ICIR_ROLLING_WINDOW", 20)
    auto_inject_on_startup: bool = _env_bool("QUANT_AUTO_INJECT_ON_STARTUP", True)
    min_history_days: int = _env_int("QUANT_MIN_HISTORY_DAYS", 5)


# ─── ChromaDB 配置 ────────────────────────────────────
class ChromaDBConfig(BaseModel):
    """ChromaDB 嵌入式向量数据库配置"""
    persist_dir: str = _env_str("CHROMADB_PERSIST_DIR", str(DATA_DIR / "chromadb"))
    retention_days: int = _env_int("CHROMADB_RETENTION_DAYS", 90)


# ─── 信息引擎配置 ─────────────────────────────────────
class InfoConfig(BaseModel):
    """信息引擎配置"""
    news_cache_hours: int = _env_int("INFO_NEWS_CACHE_HOURS", 24)
    announcement_cache_hours: int = _env_int("INFO_ANNOUNCEMENT_CACHE_HOURS", 48)
    default_news_limit: int = _env_int("INFO_DEFAULT_NEWS_LIMIT", 50)
    default_announcement_limit: int = _env_int("INFO_DEFAULT_ANNOUNCEMENT_LIMIT", 20)
    sentiment_mode: str = _env_str("INFO_SENTIMENT_MODE", "auto")


# ─── RAG 配置 ─────────────────────────────────────────
class RAGConfig(BaseModel):
    """RAG 历史报告检索配置"""
    persist_dir: str = _env_str("RAG_PERSIST_DIR", str(DATA_DIR / "chromadb_rag"))
    search_top_k: int = _env_int("RAG_SEARCH_TOP_K", 3)


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
    info: InfoConfig = InfoConfig()
    rag: RAGConfig = RAGConfig()


# 全局单例
settings = AppConfig()
