"""
聚类引擎 — HDBSCAN v2.0

特点：
1. 自动发现簇数（无需人工指定 K 值）
2. 噪声识别（标记离群个股）
3. 层次聚类树（支持多粒度分析）
4. 簇稳定性评分
5. v2.0: 聚类质量评分（Silhouette + Calinski-Harabasz）
6. v2.0: 可解释特征画像（原始特征均值替代 PCA 均值）
7. v2.0: 自动聚类语义标签
"""

import numpy as np
import pandas as pd
from loguru import logger

from config import settings


class ClusterQualityMetrics:
    """聚类质量评估指标"""

    def __init__(self):
        self.silhouette_score: float = 0.0
        self.calinski_harabasz: float = 0.0
        self.noise_ratio: float = 0.0
        self.n_clusters: int = 0
        self.avg_cluster_size: float = 0.0

    def to_dict(self) -> dict:
        return {
            "silhouette_score": round(self.silhouette_score, 4),
            "calinski_harabasz": round(self.calinski_harabasz, 2),
            "noise_ratio": round(self.noise_ratio, 4),
            "n_clusters": self.n_clusters,
            "avg_cluster_size": round(self.avg_cluster_size, 1),
        }


class ClusterEngine:
    """HDBSCAN 聚类引擎 v2.0"""

    def __init__(self):
        self._model = None
        self._labels = None
        self._probabilities = None
        self._quality: ClusterQualityMetrics | None = None

    def fit(self, X: np.ndarray) -> np.ndarray:
        """
        对特征矩阵进行聚类
        
        Args:
            X: (n_stocks, n_features) 标准化后的特征矩阵
            
        Returns:
            labels: (n_stocks,) 聚类标签，-1 表示噪声点
        """
        import hdbscan

        cfg = settings.hdbscan
        logger.info(
            f"HDBSCAN 聚类开始: {X.shape[0]} 个样本, {X.shape[1]} 维特征 | "
            f"min_cluster_size={cfg.min_cluster_size}, min_samples={cfg.min_samples}"
        )

        self._model = hdbscan.HDBSCAN(
            min_cluster_size=cfg.min_cluster_size,
            min_samples=cfg.min_samples,
            metric=cfg.metric,
            cluster_selection_method=cfg.cluster_selection_method,
            core_dist_n_jobs=-1,  # 多核并行
        )

        self._model.fit(X)
        self._labels = self._model.labels_
        self._probabilities = self._model.probabilities_

        # 统计聚类结果
        n_clusters = len(set(self._labels)) - (1 if -1 in self._labels else 0)
        n_noise = int(np.sum(self._labels == -1))
        
        logger.info(
            f"HDBSCAN 聚类完成: "
            f"发现 {n_clusters} 个簇, "
            f"{n_noise} 个噪声点 ({n_noise / len(self._labels) * 100:.1f}%)"
        )

        # 输出每个簇的大小
        for label in sorted(set(self._labels)):
            if label == -1:
                continue
            count = int(np.sum(self._labels == label))
            avg_prob = float(np.mean(self._probabilities[self._labels == label]))
            logger.debug(f"  簇 {label}: {count} 只股票, 平均置信度 {avg_prob:.3f}")

        # v2.0: 计算聚类质量评分
        self._quality = self._compute_quality(X)

        return self._labels

    def _compute_quality(self, X: np.ndarray) -> ClusterQualityMetrics:
        """计算聚类质量评估指标"""
        from sklearn.metrics import silhouette_score, calinski_harabasz_score

        metrics = ClusterQualityMetrics()
        if self._labels is None:
            return metrics

        n_clusters = len(set(self._labels)) - (1 if -1 in self._labels else 0)
        n_noise = int(np.sum(self._labels == -1))
        non_noise_count = len(self._labels) - n_noise

        metrics.n_clusters = n_clusters
        metrics.noise_ratio = n_noise / len(self._labels) if len(self._labels) > 0 else 0
        metrics.avg_cluster_size = non_noise_count / n_clusters if n_clusters > 0 else 0

        if n_clusters < 2:
            logger.warning("聚类数 < 2，无法计算 Silhouette/CH 分数")
            return metrics

        # 仅对非噪声点计算（噪声标签 -1 会导致指标失真）
        non_noise_mask = self._labels != -1
        if np.sum(non_noise_mask) < 10:
            logger.warning("非噪声点太少，跳过质量评估")
            return metrics

        X_clean = X[non_noise_mask]
        labels_clean = self._labels[non_noise_mask]

        try:
            # Silhouette: [-1, 1]，越高越好，>0.5 优秀，>0.25 合理
            # 样本量大时用采样加速
            sample_size = min(5000, len(X_clean))
            metrics.silhouette_score = float(silhouette_score(
                X_clean, labels_clean, sample_size=sample_size, random_state=42
            ))
        except Exception as e:
            logger.warning(f"Silhouette 计算失败: {e}")

        try:
            # Calinski-Harabasz: 越高越好，无上限，通常 > 50 就不错
            metrics.calinski_harabasz = float(calinski_harabasz_score(
                X_clean, labels_clean
            ))
        except Exception as e:
            logger.warning(f"Calinski-Harabasz 计算失败: {e}")

        logger.info(
            f"📊 聚类质量评分: "
            f"Silhouette={metrics.silhouette_score:.4f}, "
            f"CH={metrics.calinski_harabasz:.1f}, "
            f"噪声率={metrics.noise_ratio:.1%}"
        )

        return metrics

    def get_cluster_summary(
        self,
        meta_df: pd.DataFrame,
        X: np.ndarray,
        feature_names: list[str],
        raw_features_df: pd.DataFrame | None = None,
        raw_feature_cols: list[str] | None = None,
    ) -> list[dict]:
        """
        生成聚类摘要 v2.0

        v2.0 增强：
        - raw_features_df: 原始特征（未 PCA/标准化），用于生成可解释 feature_profile
        - 自动生成聚类语义标签

        Returns:
            [{
                "cluster_id": 0,
                "size": 120,
                "avg_probability": 0.85,
                "center": [0.1, -0.3, ...],
                "top_stocks": ["贵州茅台", "五粮液", ...],
                "feature_profile": {"avg_pe_ttm": 25.3, "avg_turnover_rate": 3.2, ...},
                "label": "高换手科技股",
            }, ...]
        """
        if self._labels is None:
            raise ValueError("请先调用 fit()")

        summaries = []
        unique_labels = sorted(set(self._labels))

        for label in unique_labels:
            mask = self._labels == label
            cluster_X = X[mask]
            cluster_meta = meta_df[mask]
            cluster_probs = self._probabilities[mask]

            summary = {
                "cluster_id": int(label),
                "is_noise": bool(label == -1),
                "size": int(np.sum(mask)),
                "avg_probability": float(np.mean(cluster_probs)),
                "center": [float(v) for v in cluster_X.mean(axis=0)],
                "top_stocks": [str(s) for s in cluster_meta["name"].head(5).tolist()],
                "stock_codes": [str(c) for c in cluster_meta["code"].tolist()],
            }

            # v2.0: 可解释特征画像 — 使用原始特征的簇内均值
            if raw_features_df is not None and raw_feature_cols:
                profile = {}
                cluster_raw = raw_features_df.loc[mask, raw_feature_cols]
                for col in raw_feature_cols:
                    if col in cluster_raw.columns:
                        vals = pd.to_numeric(cluster_raw[col], errors="coerce")
                        profile[f"avg_{col}"] = round(float(vals.mean()), 4) if not vals.isna().all() else 0.0
                        profile[f"std_{col}"] = round(float(vals.std()), 4) if len(vals.dropna()) > 1 else 0.0
                summary["feature_profile"] = profile
            elif feature_names:
                # fallback: PCA 特征均值
                profile = {}
                for i, fname in enumerate(feature_names):
                    if i < cluster_X.shape[1]:
                        profile[fname] = float(np.mean(cluster_X[:, i]))
                summary["feature_profile"] = profile

            # v2.0: 自动聚类语义标签
            if raw_features_df is not None and raw_feature_cols and not summary["is_noise"]:
                summary["label"] = self._generate_cluster_label(
                    raw_features_df, mask, raw_feature_cols,
                    raw_features_df.loc[:, raw_feature_cols] if raw_feature_cols else None,
                )
            else:
                summary["label"] = "离群股" if summary["is_noise"] else f"板块 {label}"

            summaries.append(summary)

        return summaries

    @staticmethod
    def _generate_cluster_label(
        raw_df: pd.DataFrame,
        mask: np.ndarray,
        feature_cols: list[str],
        global_df: pd.DataFrame | None = None,
    ) -> str:
        """
        根据簇内特征与全局特征的偏差自动生成可读标签

        策略：找出偏差最大的 2 个特征维度，组合成标签
        """
        if global_df is None or global_df.empty:
            return "未知板块"

        # 映射特征名到中文描述
        FEATURE_CN = {
            "pe_ttm": "PE", "pb": "PB", "total_mv": "大市值", "circ_mv": "大流通",
            "turnover_rate": "活跃", "pct_chg": "强势",
            "volatility_20d": "高波动", "volatility_60d": "高波动",
            "momentum_20d": "高动量", "rsi_14": "超买",
            "ma_deviation_20": "偏离均线", "ma_deviation_60": "偏离60均线",
        }
        FEATURE_CN_LOW = {
            "pe_ttm": "低PE", "pb": "低PB", "total_mv": "小市值", "circ_mv": "小流通",
            "turnover_rate": "低换手", "pct_chg": "弱势",
            "volatility_20d": "低波动", "volatility_60d": "低波动",
            "momentum_20d": "下跌趋势", "rsi_14": "超卖",
            "ma_deviation_20": "贴近均线", "ma_deviation_60": "贴近60均线",
        }

        deviations = []
        for col in feature_cols:
            if col not in raw_df.columns:
                continue
            cluster_vals = pd.to_numeric(raw_df.loc[mask, col], errors="coerce")
            global_vals = pd.to_numeric(global_df[col], errors="coerce")

            c_mean = cluster_vals.mean()
            g_mean = global_vals.mean()
            g_std = global_vals.std()

            if pd.isna(c_mean) or pd.isna(g_mean) or g_std == 0 or pd.isna(g_std):
                continue

            z_score = (c_mean - g_mean) / g_std
            deviations.append((col, z_score))

        if not deviations:
            return "综合板块"

        # 按偏差绝对值排序，取 top 2
        deviations.sort(key=lambda x: abs(x[1]), reverse=True)
        parts = []
        for col, z in deviations[:2]:
            if abs(z) < 0.3:
                continue
            if z > 0:
                parts.append(FEATURE_CN.get(col, col))
            else:
                parts.append(FEATURE_CN_LOW.get(col, f"低{col}"))

        return "·".join(parts) if parts else "综合板块"

    @property
    def labels(self) -> np.ndarray | None:
        return self._labels

    @property
    def probabilities(self) -> np.ndarray | None:
        return self._probabilities

    @property
    def quality(self) -> ClusterQualityMetrics | None:
        return self._quality

    @property
    def n_clusters(self) -> int:
        if self._labels is None:
            return 0
        return len(set(self._labels)) - (1 if -1 in self._labels else 0)
