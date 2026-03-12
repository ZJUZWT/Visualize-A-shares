"""
特征工程模块 v3.0 — 语义嵌入 + 数值特征融合

架构：
  Layer 1: BGE 语义嵌入 (768 维) × 权重 2.0 — 公司经营范围语义相似度
  Layer 2: 数值特征 (6 维) × 权重 1.0 — 财务/交易特征

融合后 → PCA 降到 50 维 → 输入 HDBSCAN + UMAP

v3.0 变更：
  - 去掉行业 one-hot 硬分类层（避免行业主导聚类）
  - 行业信息融入 BGE 嵌入文本（作为语义上下文）
  - 公司概况数据改用 company_profiles.json
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA


# ─── 路径 ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PRECOMPUTED_DIR = PROJECT_ROOT / "data" / "precomputed"


# ─── 特征定义 ──────────────────────────────────────────

# 可直接从快照获取的特征
SNAPSHOT_FEATURES = [
    "pe_ttm",
    "pb",
    "total_mv",
    "circ_mv",
    "turnover_rate",
    "pct_chg",
]

# 需要从日线历史计算的技术特征
COMPUTED_FEATURES = [
    "volatility_20d",
    "volatility_60d",
    "momentum_20d",
    "rsi_14",
    "ma_deviation_20",
    "ma_deviation_60",
]

ALL_FEATURES = SNAPSHOT_FEATURES + COMPUTED_FEATURES


# ─── 三层融合权重（v3.0 调整版）─────────────────────
WEIGHT_INDUSTRY = 0.8   # 行业 one-hot 权重（降低，作为软提示）
WEIGHT_EMBEDDING = 1.5  # BGE 语义嵌入权重
WEIGHT_NUMERIC = 1.0    # 数值特征权重
EMBEDDING_PCA_DIM = 32  # 嵌入先降到此维度（解决维度不平衡）
PCA_TARGET_DIM = 50     # 最终 PCA 降维目标维度


class PrecomputedData:
    """预计算数据加载器 v3.0"""

    def __init__(self):
        self.available = False
        self.profiles: dict = {}        # {code: {name, industry, scope, ...}}
        self.embedding_codes: np.ndarray | None = None
        self.embeddings: np.ndarray | None = None
        self.embedding_dim: int = 0
        self._load()

    def _load(self):
        """尝试加载预计算文件"""
        profiles_path = PRECOMPUTED_DIR / "company_profiles.json"
        embedding_path = PRECOMPUTED_DIR / "stock_embeddings.npz"

        # v3.0: 优先用 company_profiles.json
        # 兼容 v2.0: 如果没有 profiles 但有 industry_mapping 也算可用
        if profiles_path.exists():
            try:
                with open(profiles_path, "r", encoding="utf-8") as f:
                    self.profiles = json.load(f)
                logger.info(
                    f"📋 公司概况加载: {len(self.profiles)} 只股票"
                )
            except Exception as e:
                logger.warning(f"公司概况加载失败: {e}")
        else:
            # 兼容 v2.0 的 industry_mapping.json
            industry_path = PRECOMPUTED_DIR / "industry_mapping.json"
            if industry_path.exists():
                try:
                    with open(industry_path, "r", encoding="utf-8") as f:
                        industry_mapping = json.load(f)
                    # 转换为 profiles 格式
                    for code, info in industry_mapping.items():
                        self.profiles[code] = {
                            "code": code,
                            "industry": info.get("industry_name", ""),
                        }
                    logger.info(
                        f"📋 兼容 v2.0 行业映射: {len(self.profiles)} 只"
                    )
                except Exception:
                    pass

        # 加载嵌入
        if embedding_path.exists():
            try:
                data = np.load(embedding_path, allow_pickle=True)
                self.embedding_codes = data["codes"]
                self.embeddings = data["embeddings"]
                self.embedding_dim = self.embeddings.shape[1]
                model_name = (
                    str(data["model_name"])
                    if "model_name" in data
                    else "unknown"
                )
                logger.info(
                    f"🧠 嵌入加载: {self.embeddings.shape} "
                    f"(模型: {model_name})"
                )
            except Exception as e:
                logger.warning(f"嵌入加载失败: {e}")

        # 必须有嵌入数据才算可用
        if self.embeddings is not None and len(self.embeddings) > 0:
            self.available = True
            logger.info("✅ 预计算数据加载完成 — 语义嵌入融合模式")
        elif len(self.profiles) > 0:
            logger.warning(
                "⚠️ 有公司概况但无嵌入向量，退化为纯数值特征模式。"
                "请运行: python -m preprocess.build_embeddings"
            )
        else:
            logger.warning(
                "⚠️ 预计算文件不存在，使用纯数值特征模式。"
                "运行 python -m preprocess.build_embeddings 生成数据。"
            )

    def get_embeddings_for_codes(self, codes: list[str]) -> np.ndarray | None:
        """
        根据股票代码列表返回对应的嵌入向量
        对于没有嵌入的股票，返回零向量
        """
        if self.embeddings is None or self.embedding_codes is None:
            return None

        code_to_idx = {
            str(c): i for i, c in enumerate(self.embedding_codes)
        }

        result = np.zeros(
            (len(codes), self.embedding_dim), dtype=np.float32
        )
        matched = 0
        for i, code in enumerate(codes):
            idx = code_to_idx.get(str(code))
            if idx is not None:
                result[i] = self.embeddings[idx]
                matched += 1

        logger.debug(
            f"嵌入匹配: {matched}/{len(codes)} "
            f"({matched / len(codes) * 100:.1f}%)"
        )
        return result

    def get_industry_onehot_for_codes(self, codes: list[str]) -> np.ndarray | None:
        """
        根据股票代码列表返回行业 one-hot 矩阵
        从 company_profiles.json 的行业字段动态构建
        """
        if not self.profiles:
            return None

        # 收集所有出现的行业
        all_industries = sorted(set(
            p.get("industry", "") for p in self.profiles.values()
            if p.get("industry")
        ))
        if not all_industries:
            return None

        industry_to_idx = {name: i for i, name in enumerate(all_industries)}

        result = np.zeros((len(codes), len(all_industries)), dtype=np.float32)
        matched = 0
        for i, code in enumerate(codes):
            profile = self.profiles.get(str(code), {})
            industry = profile.get("industry", "")
            if industry in industry_to_idx:
                result[i, industry_to_idx[industry]] = 1.0
                matched += 1

        self._industry_names = all_industries
        logger.debug(
            f"行业 one-hot 匹配: {matched}/{len(codes)} "
            f"({matched / len(codes) * 100:.1f}%), "
            f"{len(all_industries)} 个行业"
        )
        return result

    @property
    def industry_names(self) -> list[str]:
        return getattr(self, "_industry_names", [])

    def get_cluster_centers_embedding(
        self, labels: np.ndarray, codes: list[str]
    ) -> dict[int, np.ndarray] | None:
        """
        计算每个聚类的嵌入中心向量 — 用于后续新闻匹配

        Returns:
            {cluster_id: center_embedding}
        """
        if self.embeddings is None or self.embedding_codes is None:
            return None

        embeddings = self.get_embeddings_for_codes(codes)
        if embeddings is None:
            return None

        centers = {}
        for label in set(labels):
            if label == -1:
                continue
            mask = labels == label
            cluster_embs = embeddings[mask]
            center = cluster_embs.mean(axis=0)
            norm = np.linalg.norm(center)
            if norm > 0:
                center = center / norm
            centers[int(label)] = center

        return centers


class FeatureEngineer:
    """特征工程引擎 v3.0 — 语义嵌入 + 数值特征融合"""

    def __init__(self):
        self._scaler = StandardScaler()
        self._pca = None
        self._fitted = False
        self._precomputed = PrecomputedData()
        self._cluster_centers_embedding: dict[int, np.ndarray] | None = None

    @property
    def precomputed(self) -> PrecomputedData:
        return self._precomputed

    @property
    def is_fusion_mode(self) -> bool:
        """是否处于语义融合模式"""
        return self._precomputed.available

    @property
    def cluster_centers_embedding(self) -> dict[int, np.ndarray] | None:
        """聚类中心的嵌入向量 — 用于新闻匹配"""
        return self._cluster_centers_embedding

    def extract_from_snapshot(self, snapshot_df: pd.DataFrame) -> pd.DataFrame:
        """
        从实时行情快照中提取特征

        输入: get_realtime_quotes() 的结果
        输出: code + 多维特征列的 DataFrame
        """
        if snapshot_df.empty:
            return pd.DataFrame()

        df = snapshot_df.copy()

        if "code" not in df.columns:
            logger.error("快照缺少 code 列")
            return pd.DataFrame()

        feature_cols = ["code", "name"]
        for col in SNAPSHOT_FEATURES:
            if col in df.columns:
                feature_cols.append(col)
            else:
                df[col] = np.nan
                feature_cols.append(col)

        result = df[feature_cols].copy()

        # 对数变换市值
        for mv_col in ["total_mv", "circ_mv"]:
            if mv_col in result.columns:
                result[f"{mv_col}"] = np.log1p(result[mv_col].clip(lower=0))

        logger.info(
            f"快照特征提取完成: {len(result)} 只股票, "
            f"{len(feature_cols) - 2} 维特征"
        )
        return result

    @staticmethod
    def compute_technical_features(daily_df: pd.DataFrame) -> dict:
        """从单只股票的日线数据计算技术面特征"""
        if daily_df.empty or len(daily_df) < 20:
            return {}

        close = daily_df["close"].values.astype(float)
        pct = (
            daily_df["pct_chg"].values.astype(float)
            if "pct_chg" in daily_df.columns
            else np.diff(close) / close[:-1] * 100
        )

        features = {}

        if len(pct) >= 20:
            features["volatility_20d"] = float(
                np.nanstd(pct[-20:]) * np.sqrt(252)
            )
        if len(pct) >= 60:
            features["volatility_60d"] = float(
                np.nanstd(pct[-60:]) * np.sqrt(252)
            )
        if len(close) >= 21:
            features["momentum_20d"] = float(
                (close[-1] / close[-21] - 1) * 100
            )
        if len(pct) >= 15:
            features["rsi_14"] = float(_compute_rsi(pct, 14))
        if len(close) >= 20:
            ma20 = np.mean(close[-20:])
            features["ma_deviation_20"] = float(
                (close[-1] / ma20 - 1) * 100
            )
        if len(close) >= 60:
            ma60 = np.mean(close[-60:])
            features["ma_deviation_60"] = float(
                (close[-1] / ma60 - 1) * 100
            )

        return features

    def build_feature_matrix(
        self,
        snapshot_df: pd.DataFrame,
        feature_cols: list[str] | None = None,
        weight_embedding: float | None = None,
        weight_industry: float | None = None,
        weight_numeric: float | None = None,
        pca_target_dim: int | None = None,
        embedding_pca_dim: int | None = None,
    ) -> tuple[pd.DataFrame, np.ndarray, list[str]]:
        """
        构建标准化特征矩阵

        v3.0: BGE 嵌入 + 数值特征两层融合 + PCA 降维
        支持运行时权重调节
        fallback: 纯数值特征

        Returns:
            meta_df: 包含 code, name 的元信息
            X: (n_stocks, n_features) 标准化后的特征矩阵
            feature_names: 使用的特征名列表
        """
        features_df = self.extract_from_snapshot(snapshot_df)

        if features_df.empty:
            return pd.DataFrame(), np.array([]), []

        if feature_cols is None:
            feature_cols = [
                c for c in SNAPSHOT_FEATURES if c in features_df.columns
            ]

        meta_df = features_df[["code", "name"]].copy()
        codes = meta_df["code"].tolist()

        # 数值特征矩阵
        X_numeric = features_df[feature_cols].values.astype(float)

        # 缺失值填充
        col_medians = np.nanmedian(X_numeric, axis=0)
        for j in range(X_numeric.shape[1]):
            mask = np.isnan(X_numeric[:, j])
            X_numeric[mask, j] = (
                col_medians[j] if not np.isnan(col_medians[j]) else 0.0
            )

        # Winsorize 1%/99%
        for j in range(X_numeric.shape[1]):
            p1, p99 = np.percentile(X_numeric[:, j], [1, 99])
            X_numeric[:, j] = np.clip(X_numeric[:, j], p1, p99)

        # 标准化
        X_numeric_scaled = self._scaler.fit_transform(X_numeric)

        # ─── 两层特征融合 ─────────────────────────────
        if self._precomputed.available:
            X_final, feature_names = self._fuse_features(
                codes, X_numeric_scaled, feature_cols,
                weight_embedding=weight_embedding,
                weight_industry=weight_industry,
                weight_numeric=weight_numeric,
                pca_target_dim=pca_target_dim,
                embedding_pca_dim=embedding_pca_dim,
            )
        else:
            X_final = X_numeric_scaled
            feature_names = feature_cols
            logger.info("⚠️ 使用纯数值特征模式（无预计算数据）")

        self._fitted = True

        logger.info(
            f"特征矩阵构建完成: {X_final.shape[0]} 只股票, "
            f"{X_final.shape[1]} 维特征 "
            f"({'语义嵌入融合+PCA' if self._precomputed.available else '纯数值'})"
        )

        return meta_df, X_final, feature_names

    def _fuse_features(
        self,
        codes: list[str],
        X_numeric_scaled: np.ndarray,
        numeric_feature_names: list[str],
        weight_embedding: float | None = None,
        weight_industry: float | None = None,
        weight_numeric: float | None = None,
        pca_target_dim: int | None = None,
        embedding_pca_dim: int | None = None,
    ) -> tuple[np.ndarray, list[str]]:
        """
        三层特征融合 v3.0 — 支持运行时动态权重

        Layer 1: BGE 嵌入 768d → PCA → 标准化 × weight_embedding
        Layer 2: 行业 one-hot × weight_industry
        Layer 3: 数值特征 × weight_numeric
        → concat → PCA → pca_target_dim 维
        """
        # 使用传入的权重，未传入则用全局默认值
        w_emb = weight_embedding if weight_embedding is not None else WEIGHT_EMBEDDING
        w_ind = weight_industry if weight_industry is not None else WEIGHT_INDUSTRY
        w_num = weight_numeric if weight_numeric is not None else WEIGHT_NUMERIC
        target_dim = pca_target_dim if pca_target_dim is not None else PCA_TARGET_DIM
        emb_dim = embedding_pca_dim if embedding_pca_dim is not None else EMBEDDING_PCA_DIM

        logger.info(
            f"🔗 执行三层特征融合 v3.0 "
            f"(嵌入={w_emb}, 行业={w_ind}, 数值={w_num}, "
            f"PCA={target_dim}, 嵌入PCA={emb_dim})..."
        )

        layers = []
        feature_names = []

        # Layer 1: BGE 嵌入 → 先降维
        X_embedding = self._precomputed.get_embeddings_for_codes(codes)
        if X_embedding is not None and w_emb > 0:
            actual_emb_dim = min(
                emb_dim, X_embedding.shape[1], X_embedding.shape[0] - 1
            )
            emb_pca = PCA(n_components=actual_emb_dim, random_state=42)
            X_emb_reduced = emb_pca.fit_transform(X_embedding)
            emb_var = sum(emb_pca.explained_variance_ratio_) * 100

            emb_scaler = StandardScaler()
            X_emb_scaled = emb_scaler.fit_transform(X_emb_reduced)
            X_emb_weighted = X_emb_scaled * w_emb

            layers.append(X_emb_weighted)
            feature_names.extend(
                [f"emb_{i}" for i in range(actual_emb_dim)]
            )
            logger.info(
                f"  Layer 1 — 语义嵌入: {X_embedding.shape[1]}d "
                f"→ PCA {actual_emb_dim}d (方差 {emb_var:.1f}%) "
                f"× {w_emb}"
            )

        # Layer 2: 行业 one-hot（从 profiles 动态构建）
        if w_ind > 0:
            X_industry = self._precomputed.get_industry_onehot_for_codes(codes)
            if X_industry is not None:
                X_industry_weighted = X_industry * w_ind
                layers.append(X_industry_weighted)
                feature_names.extend(
                    [f"ind_{name}" for name in self._precomputed.industry_names]
                )
                logger.info(
                    f"  Layer 2 — 行业 one-hot: {X_industry.shape[1]} 维 × {w_ind}"
                )

        # Layer 3: 数值特征
        X_numeric_weighted = X_numeric_scaled * w_num
        layers.append(X_numeric_weighted)
        feature_names.extend(
            [f"num_{name}" for name in numeric_feature_names]
        )
        logger.info(
            f"  Layer 3 — 数值特征: {X_numeric_scaled.shape[1]} 维 × {w_num}"
        )

        # 拼接
        X_concat = np.hstack(layers)
        logger.info(f"  融合后总维度: {X_concat.shape[1]}")

        # 最终 PCA 降维
        if X_concat.shape[1] > target_dim:
            actual_target = min(
                target_dim, X_concat.shape[1], X_concat.shape[0] - 1
            )
            logger.info(f"  最终 PCA: {X_concat.shape[1]} → {actual_target}")

            self._pca = PCA(n_components=actual_target, random_state=42)
            X_final = self._pca.fit_transform(X_concat)

            explained_var = sum(self._pca.explained_variance_ratio_) * 100
            logger.info(f"  PCA 解释方差: {explained_var:.1f}%")
        else:
            X_final = X_concat

        # 最终标准化
        final_scaler = StandardScaler()
        X_final = final_scaler.fit_transform(X_final)

        pca_feature_names = [f"PC_{i + 1}" for i in range(X_final.shape[1])]

        return X_final, pca_feature_names

    def compute_cluster_centers(
        self, labels: np.ndarray, codes: list[str]
    ):
        """计算聚类中心嵌入 — 用于新闻匹配"""
        self._cluster_centers_embedding = (
            self._precomputed.get_cluster_centers_embedding(labels, codes)
        )
        if self._cluster_centers_embedding:
            logger.info(
                f"📍 聚类中心嵌入计算完成: "
                f"{len(self._cluster_centers_embedding)} 个聚类中心"
            )


def _compute_rsi(pct_changes: np.ndarray, period: int = 14) -> float:
    """计算 RSI 指标"""
    if len(pct_changes) < period + 1:
        return 50.0

    recent = pct_changes[-period:]
    gains = np.where(recent > 0, recent, 0)
    losses = np.where(recent < 0, -recent, 0)

    avg_gain = np.mean(gains)
    avg_loss = np.mean(losses)

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)
