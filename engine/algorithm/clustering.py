"""
聚类引擎 — HDBSCAN

特点：
1. 自动发现簇数（无需人工指定 K 值）
2. 噪声识别（标记离群个股）
3. 层次聚类树（支持多粒度分析）
4. 簇稳定性评分
"""

import numpy as np
import pandas as pd
from loguru import logger

from config import settings


class ClusterEngine:
    """HDBSCAN 聚类引擎"""

    def __init__(self):
        self._model = None
        self._labels = None
        self._probabilities = None

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

        return self._labels

    def get_cluster_summary(
        self, meta_df: pd.DataFrame, X: np.ndarray, feature_names: list[str]
    ) -> list[dict]:
        """
        生成聚类摘要
        
        Returns:
            [{
                "cluster_id": 0,
                "size": 120,
                "avg_probability": 0.85,
                "center": [0.1, -0.3, ...],
                "top_stocks": ["贵州茅台", "五粮液", ...],
                "feature_profile": {"pe_ttm": 25.3, "volatility": 0.3, ...}
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

            # 特征画像（簇内均值）
            if feature_names:
                profile = {}
                for i, fname in enumerate(feature_names):
                    if i < cluster_X.shape[1]:
                        profile[fname] = float(np.mean(cluster_X[:, i]))
                summary["feature_profile"] = profile

            summaries.append(summary)

        return summaries

    @property
    def labels(self) -> np.ndarray | None:
        return self._labels

    @property
    def probabilities(self) -> np.ndarray | None:
        return self._probabilities

    @property
    def n_clusters(self) -> int:
        if self._labels is None:
            return 0
        return len(set(self._labels)) - (1 if -1 in self._labels else 0)
