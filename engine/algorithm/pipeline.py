"""
算法编排流水线 v2.0

将特征工程 → 聚类 → 降维 → Wendland核密度插值 串联为统一的 pipeline
一键生成前端所需的全部 3D 地形数据

v2.0 新增:
- 多指标一次性预计算（Z轴切换零延迟）
- Wendland C2 核密度地形（替代 RBF）
- 支持 radius_scale 前端滑块控制
"""

import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from loguru import logger

from .features import FeatureEngineer
from .clustering import ClusterEngine
from .projection import ProjectionEngine
from .interpolation import InterpolationEngine


# 所有可用的 Z 轴指标
Z_METRICS = ["pct_chg", "turnover_rate", "volume", "amount", "pe_ttm", "pb"]


@dataclass
class TerrainResult:
    """地形计算结果 — 前端所需的全部数据 (v2.0)"""

    # 离散股票点
    stocks: list[dict] = field(default_factory=list)
    # 聚类摘要
    clusters: list[dict] = field(default_factory=list)
    
    # v2.0: 多指标地形网格 { metric_name: flat_grid }
    grids: dict[str, list[float]] = field(default_factory=dict)
    # v2.0: 每个指标的 Z 轴范围
    bounds_per_metric: dict[str, dict] = field(default_factory=dict)
    
    # 当前活跃指标的网格（兼容 v1 前端）
    terrain_grid: list[float] = field(default_factory=list)
    terrain_resolution: int = 128
    
    # 空间边界
    bounds: dict = field(default_factory=dict)
    
    # 元数据
    stock_count: int = 0
    cluster_count: int = 0
    computation_time_ms: float = 0
    active_metric: str = "pct_chg"


class AlgorithmPipeline:
    """
    算法总编排器 v2.0
    
    流水线：
    snapshot → 特征提取 → HDBSCAN聚类 → UMAP降维 → Wendland核密度插值(多指标) → TerrainResult
    """

    def __init__(self):
        self.feature_eng = FeatureEngineer()
        self.cluster_eng = ClusterEngine()
        self.projection_eng = ProjectionEngine()
        self.interpolation_eng = InterpolationEngine()

        # 缓存
        self._last_result: TerrainResult | None = None
        self._last_meta_df: pd.DataFrame | None = None
        self._last_embedding: np.ndarray | None = None
        self._last_snapshot: pd.DataFrame | None = None

    def compute_full(
        self,
        snapshot_df: pd.DataFrame,
        z_column: str = "pct_chg",
        feature_cols: list[str] | None = None,
        grid_resolution: int = 128,
        radius_scale: float = 2.0,
        weight_embedding: float | None = None,
        weight_industry: float | None = None,
        weight_numeric: float | None = None,
        pca_target_dim: int | None = None,
        embedding_pca_dim: int | None = None,
    ) -> TerrainResult:
        """
        全量计算流水线 (v3.0)
        
        - 一次性计算所有 Z 轴指标的地形网格
        - 使用 Wendland C2 核密度场
        - 支持运行时聚类权重调节
        """
        t0 = time.time()
        logger.info("=" * 60)
        logger.info("🏔️  算法流水线 v3.0 启动 — 全量计算")
        logger.info("=" * 60)

        # ─── Step 1: 特征提取 ─────────────────────────
        logger.info("📊 Step 1/4: 特征提取...")
        meta_df, X, feature_names = self.feature_eng.build_feature_matrix(
            snapshot_df, feature_cols,
            weight_embedding=weight_embedding,
            weight_industry=weight_industry,
            weight_numeric=weight_numeric,
            pca_target_dim=pca_target_dim,
            embedding_pca_dim=embedding_pca_dim,
        )

        if X.size == 0:
            logger.error("特征矩阵为空，流水线终止")
            return TerrainResult()

        # ─── Step 2: HDBSCAN 聚类 ─────────────────────
        logger.info("🔬 Step 2/4: HDBSCAN 聚类...")
        labels = self.cluster_eng.fit(X)
        cluster_summaries = self.cluster_eng.get_cluster_summary(
            meta_df, X, feature_names
        )

        # 计算聚类中心嵌入（用于后续新闻匹配）
        self.feature_eng.compute_cluster_centers(
            labels, meta_df["code"].tolist()
        )

        # ─── Step 3: UMAP 降维 ───────────────────────
        logger.info("🗺️  Step 3/4: UMAP 2D 降维...")
        embedding = self.projection_eng.fit_transform(X)

        # ─── Step 4: 多指标 Wendland 核密度插值 ────────
        logger.info("🏔️  Step 4/4: Wendland C2 核密度地形 (多指标批量)...")
        
        # 构建多指标 Z 值字典
        z_dict = {}
        for metric in Z_METRICS:
            z_values = np.zeros(len(meta_df))
            if metric in snapshot_df.columns:
                z_map = snapshot_df.set_index("code")[metric].to_dict()
                for i, code in enumerate(meta_df["code"].values):
                    val = z_map.get(code, 0.0)
                    z_values[i] = float(val) if pd.notna(val) else 0.0
            z_dict[metric] = z_values
        
        # 一次性计算所有指标的地形
        terrain_multi = self.interpolation_eng.compute_terrain_multi(
            embedding[:, 0],
            embedding[:, 1],
            z_dict,
            resolution=grid_resolution,
            radius_scale=radius_scale,
        )

        # ─── 组装最终结果 ─────────────────────────────
        elapsed = (time.time() - t0) * 1000

        # 构建股票点列表（前端用）
        # 用 active metric 的 z 值
        active_z = z_dict.get(z_column, z_dict.get("pct_chg", np.zeros(len(meta_df))))
        
        # 获取公司概况（如果有预计算数据）
        profiles = (
            self.feature_eng.precomputed.profiles
            if self.feature_eng.is_fusion_mode
            else {}
        )

        stocks_list = []
        for i, (_, row) in enumerate(meta_df.iterrows()):
            code = str(row["code"])
            stock = {
                "code": code,
                "name": str(row["name"]),
                "x": float(embedding[i, 0]),
                "y": float(embedding[i, 1]),
                "z": float(active_z[i]),
                "cluster_id": int(labels[i]),
            }
            # 附带行业信息
            profile = profiles.get(code, {})
            if profile.get("industry"):
                stock["industry"] = profile["industry"]
            # 附带所有指标的原始值
            for metric in Z_METRICS:
                stock[f"z_{metric}"] = float(z_dict[metric][i])
            stocks_list.append(stock)

        # 给聚类摘要添加行业分布
        if profiles:
            for summary in cluster_summaries:
                cluster_codes = summary.get("stock_codes", [])
                industry_counter: dict[str, int] = {}
                for c in cluster_codes:
                    p = profiles.get(c, {})
                    ind_name = p.get("industry", "")
                    if ind_name:
                        industry_counter[ind_name] = industry_counter.get(ind_name, 0) + 1
                # 按数量排序，取 top 5
                top_industries = sorted(
                    industry_counter.items(), key=lambda x: -x[1]
                )[:5]
                summary["top_industries"] = [
                    {"name": name, "count": count}
                    for name, count in top_industries
                ]

        # 获取当前活跃指标的 bounds
        active_bounds = terrain_multi["bounds"].copy()
        metric_bounds = terrain_multi["bounds_per_metric"].get(z_column, {"zmin": 0, "zmax": 1})
        active_bounds["zmin"] = metric_bounds["zmin"]
        active_bounds["zmax"] = metric_bounds["zmax"]

        result = TerrainResult(
            stocks=stocks_list,
            clusters=cluster_summaries,
            grids=terrain_multi["grids"],
            bounds_per_metric=terrain_multi["bounds_per_metric"],
            terrain_grid=terrain_multi["grids"].get(z_column, []),
            terrain_resolution=terrain_multi["resolution"],
            bounds=active_bounds,
            stock_count=len(stocks_list),
            cluster_count=self.cluster_eng.n_clusters,
            computation_time_ms=elapsed,
            active_metric=z_column,
        )

        # 缓存
        self._last_result = result
        self._last_meta_df = meta_df
        self._last_embedding = embedding
        self._last_snapshot = snapshot_df

        logger.info(
            f"✅ 流水线完成: {result.stock_count} 只股票, "
            f"{result.cluster_count} 个簇, "
            f"{len(Z_METRICS)} 个指标 × {result.terrain_resolution}² 网格 | "
            f"耗时 {elapsed:.0f}ms"
        )
        logger.info("=" * 60)

        return result

    def update_z_axis(
        self,
        snapshot_df: pd.DataFrame,
        z_column: str = "pct_chg",
    ) -> TerrainResult | None:
        """
        快速更新 Z 轴值（保持 XY 布局不变）
        用于实时行情刷新场景
        
        v2.0: 同时更新所有指标的网格
        """
        if self._last_meta_df is None or self._last_embedding is None:
            logger.warning("尚未执行全量计算，无法增量更新")
            return None

        t0 = time.time()
        logger.info("⚡ Z 轴快速更新 (所有指标)...")

        # 重新提取所有指标的 Z 值
        z_dict = {}
        for metric in Z_METRICS:
            z_values = np.zeros(len(self._last_meta_df))
            if metric in snapshot_df.columns:
                z_map = snapshot_df.set_index("code")[metric].to_dict()
                for i, code in enumerate(self._last_meta_df["code"].values):
                    val = z_map.get(code, 0.0)
                    z_values[i] = float(val) if pd.notna(val) else 0.0
            z_dict[metric] = z_values

        # 重新计算所有指标的地形
        terrain_multi = self.interpolation_eng.compute_terrain_multi(
            self._last_embedding[:, 0],
            self._last_embedding[:, 1],
            z_dict,
        )

        # 更新股票点
        active_z = z_dict.get(z_column, z_dict.get("pct_chg", np.zeros(len(self._last_meta_df))))
        
        stocks_list = []
        for i, (_, row) in enumerate(self._last_meta_df.iterrows()):
            stock = {
                "code": str(row["code"]),
                "name": str(row["name"]),
                "x": float(self._last_embedding[i, 0]),
                "y": float(self._last_embedding[i, 1]),
                "z": float(active_z[i]),
                "cluster_id": int(self.cluster_eng.labels[i]) if self.cluster_eng.labels is not None else 0,
            }
            for metric in Z_METRICS:
                stock[f"z_{metric}"] = float(z_dict[metric][i])
            stocks_list.append(stock)

        elapsed = (time.time() - t0) * 1000

        active_bounds = terrain_multi["bounds"].copy()
        metric_bounds = terrain_multi["bounds_per_metric"].get(z_column, {"zmin": 0, "zmax": 1})
        active_bounds["zmin"] = metric_bounds["zmin"]
        active_bounds["zmax"] = metric_bounds["zmax"]

        result = TerrainResult(
            stocks=stocks_list,
            clusters=self._last_result.clusters if self._last_result else [],
            grids=terrain_multi["grids"],
            bounds_per_metric=terrain_multi["bounds_per_metric"],
            terrain_grid=terrain_multi["grids"].get(z_column, []),
            terrain_resolution=terrain_multi["resolution"],
            bounds=active_bounds,
            stock_count=len(stocks_list),
            cluster_count=self.cluster_eng.n_clusters,
            computation_time_ms=elapsed,
            active_metric=z_column,
        )

        self._last_result = result
        logger.info(f"⚡ Z 轴更新完成: {elapsed:.0f}ms")
        return result

    @property
    def last_result(self) -> TerrainResult | None:
        return self._last_result
