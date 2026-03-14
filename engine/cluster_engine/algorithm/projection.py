"""
降维投影引擎 — UMAP

职责：
1. 将多维特征空间投影到 2D 平面
2. 保留全局+局部结构，让相似股票在空间上靠近
3. 支持增量更新（新股票可直接 transform）
"""

import numpy as np
import pandas as pd
from loguru import logger

from config import settings


class ProjectionEngine:
    """UMAP 降维投影引擎"""

    def __init__(self):
        self._model = None
        self._embedding = None

    def fit_transform(self, X: np.ndarray) -> np.ndarray:
        """
        全量降维：将 N 维特征矩阵投影到 2D
        
        Args:
            X: (n_stocks, n_features) 标准化后的特征矩阵
            
        Returns:
            embedding: (n_stocks, 2) 2D 坐标
        """
        import umap

        cfg = settings.umap
        logger.info(
            f"UMAP 降维开始: {X.shape[0]} 样本, {X.shape[1]}D → 2D | "
            f"n_neighbors={cfg.n_neighbors}, min_dist={cfg.min_dist}"
        )

        self._model = umap.UMAP(
            n_neighbors=cfg.n_neighbors,
            min_dist=cfg.min_dist,
            n_components=cfg.n_components,
            metric=cfg.metric,
            random_state=cfg.random_state,
            n_epochs=cfg.n_epochs,
        )

        self._embedding = self._model.fit_transform(X)

        # 归一化到 [-1, 1] 范围，方便前端渲染
        self._embedding = self._normalize_embedding(self._embedding)

        logger.info(
            f"UMAP 降维完成: 输出形状 {self._embedding.shape}, "
            f"X范围 [{self._embedding[:, 0].min():.2f}, {self._embedding[:, 0].max():.2f}], "
            f"Y范围 [{self._embedding[:, 1].min():.2f}, {self._embedding[:, 1].max():.2f}]"
        )

        return self._embedding

    def transform(self, X_new: np.ndarray) -> np.ndarray:
        """
        增量投影：将新样本投影到已有的 2D 空间
        （无需全量重新计算）
        """
        if self._model is None:
            raise ValueError("请先调用 fit_transform()")

        new_embedding = self._model.transform(X_new)
        return self._normalize_embedding(new_embedding)

    @staticmethod
    def _normalize_embedding(
        embedding: np.ndarray, target_range: float = 10.0
    ) -> np.ndarray:
        """
        将嵌入坐标归一化到 [-target_range, target_range]
        方便 3D 渲染场景使用
        """
        result = embedding.copy()
        for dim in range(result.shape[1]):
            col = result[:, dim]
            col_min, col_max = col.min(), col.max()
            if col_max - col_min > 1e-8:
                result[:, dim] = (col - col_min) / (col_max - col_min) * 2 * target_range - target_range
        return result

    def build_projection_result(
        self,
        meta_df: pd.DataFrame,
        cluster_labels: np.ndarray | None = None,
        z_values: np.ndarray | None = None,
    ) -> pd.DataFrame:
        """
        构建投影结果 DataFrame
        
        Returns:
            DataFrame with: code, name, x, y, z, cluster_id
        """
        if self._embedding is None:
            raise ValueError("请先调用 fit_transform()")

        result = meta_df.copy().reset_index(drop=True)
        result["x"] = self._embedding[:, 0]
        result["y"] = self._embedding[:, 1]

        # Z 轴 (默认: 涨跌幅)
        if z_values is not None:
            result["z"] = z_values
        else:
            result["z"] = 0.0

        # 聚类标签
        if cluster_labels is not None:
            result["cluster_id"] = cluster_labels
        else:
            result["cluster_id"] = 0

        return result

    @property
    def embedding(self) -> np.ndarray | None:
        return self._embedding
