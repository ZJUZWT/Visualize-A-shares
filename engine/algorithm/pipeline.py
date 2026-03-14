"""
算法编排流水线 v3.0

将特征工程 → 聚类 → 降维 → 高斯核密度插值 串联为统一的 pipeline
一键生成前端所需的全部 3D 地形数据

v3.0 新增:
- 技术指标自动计算并参与聚类（波动率/动量/RSI/均线偏离）
- 聚类质量评分（Silhouette + Calinski-Harabasz）
- 可解释特征画像（原始特征均值替代 PCA 均值）
- 自动聚类语义标签
- 跨簇全局相似股票搜索（噪声点也能找到相似股）
"""

import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from loguru import logger
from scipy.spatial import cKDTree

from .features import FeatureEngineer
from .clustering import ClusterEngine
from .projection import ProjectionEngine
from .interpolation import InterpolationEngine
from .predictor import StockPredictor
from .predictor_v2 import StockPredictorV2


# 所有可用的 Z 轴指标
Z_METRICS = ["pct_chg", "turnover_rate", "volume", "amount", "pe_ttm", "pb", "wb_ratio", "rise_prob"]


@dataclass
class TerrainResult:
    """地形计算结果 — 前端所需的全部数据 (v3.0)"""

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

    # v3.0: 聚类质量评分
    cluster_quality: dict = field(default_factory=dict)


class AlgorithmPipeline:
    """
    算法总编排器 v2.0
    
    流水线：
    snapshot → 特征提取 → HDBSCAN聚类 → UMAP降维 → 高斯核密度插值(多指标) → TerrainResult
    """

    def __init__(self):
        self.feature_eng = FeatureEngineer()
        self.cluster_eng = ClusterEngine()
        self.projection_eng = ProjectionEngine()
        self.interpolation_eng = InterpolationEngine()
        self.predictor = StockPredictor()         # v1 fallback
        self.predictor_v2 = StockPredictorV2()    # v2 量化增强

        # 缓存
        self._last_result: TerrainResult | None = None
        self._last_meta_df: pd.DataFrame | None = None
        self._last_embedding: np.ndarray | None = None
        self._last_snapshot: pd.DataFrame | None = None
        self._last_X_features: np.ndarray | None = None  # v4.0: 高维特征矩阵，用于跨簇搜索
        # v3.1: 缓存上次使用的聚类参数，用于判断是否需要重做 UMAP
        self._last_params: dict | None = None
        self._last_codes_set: set[str] | None = None

    @staticmethod
    def _compute_related_stocks(
        stocks_list: list[dict],
        labels: np.ndarray,
        embedding_2d: np.ndarray,
        X_features: np.ndarray | None = None,
        top_k: int = 10,
    ) -> None:
        """
        为每只股票就地附加关联股票 v3.0

        v3.0 增强:
        - related_stocks: 同簇内最近邻（保持原有逻辑）
        - similar_stocks: 全局最近邻（跨簇搜索，使用高维特征空间距离）
        - 噪声点也能获得 similar_stocks（全局搜索不排除噪声）
        """
        t0 = time.time()

        # ─── 1. 同簇关联（原有逻辑）─────────────────────
        cluster_map: dict[int, list[int]] = {}
        for i, label in enumerate(labels):
            label_int = int(label)
            if label_int == -1:
                continue
            cluster_map.setdefault(label_int, []).append(i)

        for label, indices in cluster_map.items():
            if len(indices) <= 1:
                continue

            idx_arr = np.array(indices)
            cluster_coords = embedding_2d[idx_arr]
            tree = cKDTree(cluster_coords)

            k = min(top_k + 1, len(indices))
            distances, local_neighbors = tree.query(cluster_coords, k=k)

            for local_idx, global_idx in enumerate(indices):
                neighbors = []
                for j in range(1, k):
                    ln = local_neighbors[local_idx][j]
                    gi = indices[ln]
                    s = stocks_list[gi]
                    neighbors.append({
                        "code": s["code"],
                        "name": s["name"],
                        "industry": s.get("industry", ""),
                        "pct_chg": s.get("z_pct_chg", 0.0),
                    })
                stocks_list[global_idx]["related_stocks"] = neighbors

        # ─── 2. 全局相似股票（跨簇搜索）──────────────────
        # 使用高维特征空间距离（如果有的话），否则用 2D UMAP 距离
        search_data = X_features if X_features is not None else embedding_2d
        global_tree = cKDTree(search_data)

        gk = min(top_k + 1, len(stocks_list))
        g_distances, g_neighbors = global_tree.query(search_data, k=gk)

        for i in range(len(stocks_list)):
            similar = []
            for j in range(1, gk):
                gi = g_neighbors[i][j]
                s = stocks_list[gi]
                # 跳过同簇的（那些已经在 related_stocks 中了）
                if int(labels[i]) != -1 and int(labels[gi]) == int(labels[i]):
                    continue
                similar.append({
                    "code": s["code"],
                    "name": s["name"],
                    "industry": s.get("industry", ""),
                    "pct_chg": s.get("z_pct_chg", 0.0),
                    "cluster_id": int(labels[gi]),
                })
                if len(similar) >= 5:
                    break
            stocks_list[i]["similar_stocks"] = similar

        # 对于噪声点，如果没有 related_stocks，用全局搜索结果替代
        for i in range(len(stocks_list)):
            if not stocks_list[i].get("related_stocks"):
                # 噪声点：用全局最近邻作为关联股票
                fallback = []
                for j in range(1, gk):
                    gi = g_neighbors[i][j]
                    s = stocks_list[gi]
                    fallback.append({
                        "code": s["code"],
                        "name": s["name"],
                        "industry": s.get("industry", ""),
                        "pct_chg": s.get("z_pct_chg", 0.0),
                    })
                    if len(fallback) >= top_k:
                        break
                stocks_list[i]["related_stocks"] = fallback

        elapsed_ms = (time.time() - t0) * 1000
        logger.info(f"  关联+相似股票计算完成: {elapsed_ms:.0f}ms")

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
        on_progress: "callable | None" = None,
        daily_df_map: dict[str, pd.DataFrame] | None = None,
    ) -> TerrainResult:
        """
        全量计算流水线 (v4.0)
        
        - 一次性计算所有 Z 轴指标的地形网格
        - 使用高斯核密度场
        - 支持运行时聚类权重调节
        - v3.1: 参数不变时复用 UMAP 布局，保持地形稳定
        - v4.0: 技术指标参与聚类 + 聚类质量评分 + 可解释画像 + 跨簇搜索
        """
        t0 = time.time()
        logger.info("=" * 60)
        logger.info("🏔️  算法流水线 v4.0 启动")
        logger.info("=" * 60)

        # ─── 检查是否可以复用上次的 UMAP 布局 ─────────
        current_params = {
            "weight_embedding": weight_embedding,
            "weight_industry": weight_industry,
            "weight_numeric": weight_numeric,
            "pca_target_dim": pca_target_dim,
            "embedding_pca_dim": embedding_pca_dim,
        }

        # 计算当前股票集
        current_codes = set(snapshot_df["code"].astype(str).tolist()) if "code" in snapshot_df.columns else set()

        can_reuse_layout = False
        if (
            self._last_embedding is not None
            and self._last_meta_df is not None
            and self._last_params is not None
            and self._last_codes_set is not None
        ):
            # 检查参数是否相同
            params_same = (self._last_params == current_params)
            
            # 检查股票集重叠率
            if current_codes and self._last_codes_set:
                overlap = len(current_codes & self._last_codes_set)
                total = max(len(current_codes), len(self._last_codes_set))
                overlap_rate = overlap / total if total > 0 else 0
            else:
                overlap_rate = 0

            if params_same and overlap_rate > 0.95:
                can_reuse_layout = True
                logger.info(
                    f"♻️  检测到参数不变且股票集重叠率 {overlap_rate:.1%}，复用上次 UMAP 布局"
                )

        def _notify(step: int, total: int, step_name: str):
            if on_progress:
                try:
                    on_progress(step, total, step_name)
                except Exception:
                    pass

        cluster_quality_dict = {}

        if can_reuse_layout:
            # ─── 快速路径：复用布局，只刷新 Z 轴 ──────
            _notify(1, 4, "复用布局，刷新Z轴数据")
            meta_df = self._last_meta_df
            embedding = self._last_embedding
            labels = self.cluster_eng.labels
            cluster_summaries = self._last_result.clusters if self._last_result else []
            X_features = self._last_X_features
            cluster_quality_dict = self._last_result.cluster_quality if self._last_result else {}
        else:
            # ─── 完整路径：重新计算特征 + 聚类 + UMAP ──

            # Step 1: 特征提取（含技术指标）
            logger.info("📊 Step 1/4: 特征提取...")
            _notify(1, 4, "特征提取")
            meta_df, X, feature_names, raw_features_df, raw_feature_cols = self.feature_eng.build_feature_matrix(
                snapshot_df, feature_cols,
                weight_embedding=weight_embedding,
                weight_industry=weight_industry,
                weight_numeric=weight_numeric,
                pca_target_dim=pca_target_dim,
                embedding_pca_dim=embedding_pca_dim,
                daily_df_map=daily_df_map,
            )

            if X.size == 0:
                logger.error("特征矩阵为空，流水线终止")
                return TerrainResult()

            # Step 2: HDBSCAN 聚类
            logger.info("🔬 Step 2/4: HDBSCAN 聚类...")
            _notify(2, 4, "HDBSCAN 聚类")
            labels = self.cluster_eng.fit(X)

            # v2.0: 传递原始特征用于可解释聚类画像和语义标签
            cluster_summaries = self.cluster_eng.get_cluster_summary(
                meta_df, X, feature_names,
                raw_features_df=raw_features_df,
                raw_feature_cols=raw_feature_cols,
            )

            # v2.0: 聚类质量评分
            if self.cluster_eng.quality:
                cluster_quality_dict = self.cluster_eng.quality.to_dict()

            # 计算聚类中心嵌入
            self.feature_eng.compute_cluster_centers(
                labels, meta_df["code"].tolist()
            )

            # Step 3: UMAP 降维
            logger.info("🗺️  Step 3/4: UMAP 2D 降维...")
            _notify(3, 4, "UMAP 2D 降维")
            embedding = self.projection_eng.fit_transform(X)

            # 缓存高维特征矩阵，用于跨簇搜索
            X_features = X

        # ─── Step 4: 多指标 Wendland 核密度插值 ────────
        logger.info("🏔️  Step 4/4: 高斯核密度地形 (多指标批量)...")
        _notify(4, 4, "核密度插值")
        
        # 构建多指标 Z 值字典
        z_dict = {}
        for metric in Z_METRICS:
            if metric == "rise_prob":
                continue  # 预测概率单独处理
            z_values = np.zeros(len(meta_df))
            if metric in snapshot_df.columns:
                z_map = snapshot_df.set_index("code")[metric].to_dict()
                for i, code in enumerate(meta_df["code"].values):
                    val = z_map.get(code, 0.0)
                    z_values[i] = float(val) if pd.notna(val) else 0.0
            z_dict[metric] = z_values

        # ─── 预测：明日上涨概率 (v2.0) ─────────────────
        prediction_result = self.predictor_v2.predict(
            snapshot_df, cluster_labels=labels, daily_df_map=daily_df_map
        )
        rise_prob_values = np.zeros(len(meta_df))
        for i, code in enumerate(meta_df["code"].values):
            rise_prob_values[i] = prediction_result.predictions.get(
                str(code), 0.5
            ) - 0.5  # 减去 0.5，让 50% 成为零线，地形有正有负
        z_dict["rise_prob"] = rise_prob_values
        
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
            # v5.0: 多归属隶属度
            affinities = self.cluster_eng.get_top_affinities(i, top_k=3)
            if affinities:
                stock["cluster_affinities"] = affinities
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

        # ─── 计算关联+相似股票（v3.0: 全局搜索）────────
        self._compute_related_stocks(
            stocks_list, labels, embedding,
            X_features=X_features,
            top_k=10,
        )

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
            cluster_quality=cluster_quality_dict,
        )

        # 缓存
        self._last_result = result
        self._last_meta_df = meta_df
        self._last_embedding = embedding
        self._last_snapshot = snapshot_df
        self._last_params = current_params
        self._last_codes_set = current_codes
        self._last_X_features = X_features

        mode_str = "复用布局" if can_reuse_layout else "全量计算"
        logger.info(
            f"✅ 流水线完成 ({mode_str}): {result.stock_count} 只股票, "
            f"{result.cluster_count} 个簇, "
            f"{len(Z_METRICS)} 个指标 × {result.terrain_resolution}² 网格 | "
            f"耗时 {elapsed:.0f}ms"
        )
        if cluster_quality_dict:
            logger.info(
                f"📊 聚类质量: Silhouette={cluster_quality_dict.get('silhouette_score', 0):.4f}, "
                f"CH={cluster_quality_dict.get('calinski_harabasz', 0):.1f}"
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
