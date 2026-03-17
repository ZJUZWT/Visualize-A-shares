"""
预测模块 v2.0 — 明日上涨概率估计（量化增强版）

v1.0 → v2.0 升级要点:
  1. 因子预处理：MAD 去极值 + Z-Score 标准化（替代简单 rank normalize）
  2. 因子正交化：对共线性因子组做施密特正交化（PE/PB、turnover/amount）
  3. 因子扩充：接入 volatility_20d、momentum_20d、RSI、MA偏离等技术因子
  4. 自适应权重：基于滚动 RankIC 的 ICIR 加权（替代固定手工权重）
  5. 概率映射：正态分布 CDF（替代手动 Sigmoid + 硬编码 sensitivity）
  6. 非线性反转：只对极端涨跌(>±3%)施加反转惩罚

风险提示:
  本模型仅供学习研究，不构成任何投资建议。
  股票市场存在极高不确定性，历史因子规律不代表未来收益。
"""

import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from loguru import logger
from scipy import stats


# ─── 因子定义 ──────────────────────────────────────────

@dataclass
class FactorDef:
    """因子定义"""
    name: str               # 因子名称
    source_col: str         # 来源列名（snapshot 或 computed）
    direction: int          # +1=因子越大越看涨, -1=因子越大越看跌
    group: str = ""         # 正交化分组（同组内做施密特正交化）
    default_weight: float = 0.0  # 无 IC 数据时的默认权重
    desc: str = ""          # 描述


# 全部因子定义（13 个因子）
FACTOR_DEFS: list[FactorDef] = [
    # ── 反转因子（非线性版本，在代码中特殊处理）────
    FactorDef("reversal", "pct_chg", -1, group="momentum",
              default_weight=-0.15, desc="非线性反转：极端涨跌反转效应"),
    # ── 动量因子 ────
    FactorDef("momentum_20d", "momentum_20d", +1, group="momentum",
              default_weight=0.10, desc="20日动量"),
    # ── 换手率与成交 ────
    FactorDef("turnover", "turnover_rate", -1, group="liquidity",
              default_weight=-0.08, desc="换手率偏高→短期回落"),
    FactorDef("amount", "amount", +1, group="liquidity",
              default_weight=0.08, desc="成交额活跃→关注度正面"),
    # ── 估值因子（正交化组）────
    FactorDef("pe_value", "pe_ttm", -1, group="valuation",
              default_weight=-0.10, desc="低PE更具上涨潜力"),
    FactorDef("pb_value", "pb", -1, group="valuation",
              default_weight=-0.08, desc="低PB价值效应"),
    # ── 市值因子 ────
    FactorDef("size", "total_mv", -1, group="size",
              default_weight=-0.08, desc="小市值效应"),
    # ── 波动率因子 ────
    FactorDef("volatility", "volatility_20d", -1, group="risk",
              default_weight=-0.06, desc="低波动率异象"),
    # ── 技术因子 ────
    FactorDef("rsi", "rsi_14", -1, group="technical",
              default_weight=-0.05, desc="RSI超买超卖"),
    FactorDef("ma_dev_20", "ma_deviation_20", -1, group="technical",
              default_weight=-0.05, desc="20日均线偏离（高偏离→回归）"),
    FactorDef("ma_dev_60", "ma_deviation_60", -1, group="technical",
              default_weight=-0.03, desc="60日均线偏离"),
    # ── 板块动量（特殊因子，需要聚类信息）────
    FactorDef("cluster_momentum", "_cluster_avg_", +1, group="sector",
              default_weight=0.15, desc="同簇平均涨幅→板块联动"),
    # ── 委比因子 ────
    FactorDef("wb_ratio", "wb_ratio", +1, group="order_flow",
              default_weight=0.04, desc="委比正→买盘强"),
]


@dataclass
class PredictionResult:
    """预测结果 v2.0"""
    # { code: probability }
    predictions: dict[str, float] = field(default_factory=dict)
    # 因子明细 { code: { factor_name: score } }
    factor_details: dict[str, dict[str, float]] = field(default_factory=dict)
    # 全市场统计
    avg_probability: float = 0.0
    bullish_count: int = 0
    bearish_count: int = 0
    total_count: int = 0
    computation_time_ms: float = 0
    # v2.0 新增
    factor_weights: dict[str, float] = field(default_factory=dict)
    weight_source: str = "default"  # "default" or "icir_adaptive"


class StockPredictorV2:
    """
    多因子截面评分预测器 v2.0

    改进:
    1. MAD 去极值 + Z-Score 标准化
    2. 施密特正交化（去因子共线性）
    3. 13 因子（含技术指标）
    4. ICIR 自适应权重
    5. 正态 CDF 概率映射
    6. 非线性反转因子
    """

    def __init__(self):
        # ICIR 权重缓存（由 factor_backtest 模块写入）
        self._icir_weights: dict[str, float] | None = None
        self._weight_source: str = "default"

    def set_icir_weights(self, weights: dict[str, float]):
        """注入 ICIR 自适应权重（由回测模块调用）"""
        self._icir_weights = weights
        self._weight_source = "icir_adaptive"
        logger.info(f"📊 ICIR 权重已注入: {len(weights)} 个因子")

    def predict(
        self,
        snapshot_df: pd.DataFrame,
        cluster_labels: np.ndarray | None = None,
        daily_df_map: dict[str, pd.DataFrame] | None = None,
    ) -> PredictionResult:
        """
        计算全市场明日上涨概率 v2.0

        Args:
            snapshot_df: 实时行情快照
            cluster_labels: HDBSCAN 聚类标签
            daily_df_map: {code: daily_df} 日线历史，用于计算技术指标

        Returns:
            PredictionResult
        """
        t0 = time.time()

        if snapshot_df.empty or len(snapshot_df) < 50:
            logger.warning("快照数据不足，无法进行预测")
            return PredictionResult()

        df = snapshot_df.copy()

        if "code" not in df.columns or "pct_chg" not in df.columns:
            logger.error("快照缺少必要列: code/pct_chg")
            return PredictionResult()

        # ─── 0. 合并技术指标（如果有日线数据）──────────
        if daily_df_map:
            from engine.cluster.algorithm.features import FeatureEngineer
            for _, row in df.iterrows():
                code = str(row["code"])
                daily = daily_df_map.get(code)
                if daily is not None and not daily.empty:
                    tech = FeatureEngineer.compute_technical_features(daily)
                    for k, v in tech.items():
                        idx = df.index[df["code"] == code]
                        if len(idx) > 0:
                            df.loc[idx[0], k] = v

        # ─── 1. 提取原始因子值 ────────────────────────
        raw_factors = pd.DataFrame(index=df.index)

        for fdef in FACTOR_DEFS:
            if fdef.name == "cluster_momentum":
                # 板块动量特殊处理
                raw_factors[fdef.name] = self._compute_cluster_momentum(
                    df, cluster_labels
                )
            elif fdef.name == "reversal":
                # 非线性反转
                raw_factors[fdef.name] = self._compute_nonlinear_reversal(df)
            else:
                if fdef.source_col in df.columns:
                    raw_factors[fdef.name] = pd.to_numeric(
                        df[fdef.source_col], errors="coerce"
                    )
                else:
                    raw_factors[fdef.name] = np.nan

        # ─── 2. MAD 去极值 + Z-Score 标准化 ──────────
        processed_factors = pd.DataFrame(index=df.index)
        for col in raw_factors.columns:
            series = raw_factors[col].copy()
            series = self._mad_winsorize(series)
            series = self._zscore_standardize(series)
            processed_factors[col] = series

        # ─── 3. 施密特正交化（同组因子）───────────────
        processed_factors = self._orthogonalize_groups(processed_factors)

        # ─── 4. 应用因子方向 ──────────────────────────
        for fdef in FACTOR_DEFS:
            if fdef.name in processed_factors.columns:
                processed_factors[fdef.name] *= fdef.direction

        # ─── 5. 获取权重 ──────────────────────────────
        weights = self._get_weights()

        # ─── 6. 加权合成 ──────────────────────────────
        composite = np.zeros(len(df))
        total_abs_weight = 0.0
        for fdef in FACTOR_DEFS:
            if fdef.name in processed_factors.columns:
                w = weights.get(fdef.name, 0.0)
                vals = processed_factors[fdef.name].fillna(0.0).values
                composite += w * vals
                total_abs_weight += abs(w)

        # 归一化（让合成得分不受因子数量影响）
        if total_abs_weight > 0:
            composite /= total_abs_weight

        # ─── 7. 正态 CDF 映射为概率 ──────────────────
        # composite 已经是 Z-Score 量级，直接用正态 CDF
        probabilities = stats.norm.cdf(composite)

        # 收缩到 [0.12, 0.88]，避免极端预测
        probabilities = probabilities * 0.76 + 0.12

        # ─── 8. 组装结果 ──────────────────────────────
        predictions = {}
        factor_detail = {}
        codes = df["code"].astype(str).values

        for i, code in enumerate(codes):
            prob = float(round(probabilities[i], 4))
            predictions[code] = prob

            detail = {}
            for fdef in FACTOR_DEFS:
                if fdef.name in processed_factors.columns:
                    detail[fdef.name] = float(
                        round(processed_factors[fdef.name].iloc[i], 4)
                    )
            factor_detail[code] = detail

        probs_array = np.array(list(predictions.values()))
        elapsed = (time.time() - t0) * 1000

        result = PredictionResult(
            predictions=predictions,
            factor_details=factor_detail,
            avg_probability=float(round(probs_array.mean(), 4)),
            bullish_count=int((probs_array > 0.5).sum()),
            bearish_count=int((probs_array <= 0.5).sum()),
            total_count=len(predictions),
            computation_time_ms=elapsed,
            factor_weights=weights,
            weight_source=self._weight_source,
        )

        logger.info(
            f"🔮 预测 v2.0 完成: {result.total_count} 只股票, "
            f"看涨 {result.bullish_count} / 看跌 {result.bearish_count}, "
            f"平均概率 {result.avg_probability:.2%}, "
            f"权重来源={self._weight_source}, "
            f"耗时 {elapsed:.0f}ms"
        )

        return result

    # ─── 因子预处理工具 ───────────────────────────────────

    @staticmethod
    def _mad_winsorize(series: pd.Series, n_mad: float = 5.0) -> pd.Series:
        """
        MAD 去极值（Median Absolute Deviation）

        比百分位 Winsorize 更稳健：
        1. 计算中位数 median
        2. 计算 MAD = median(|x - median|)
        3. 上下界 = median ± n_mad * 1.4826 * MAD
        4. 超出边界的值 clip 到边界
        """
        s = series.copy()
        median = s.median()
        mad = (s - median).abs().median()
        if mad == 0 or pd.isna(mad):
            return s
        # 1.4826 是正态分布下 MAD 与标准差的换算系数
        boundary = n_mad * 1.4826 * mad
        upper = median + boundary
        lower = median - boundary
        return s.clip(lower=lower, upper=upper)

    @staticmethod
    def _zscore_standardize(series: pd.Series) -> pd.Series:
        """Z-Score 截面标准化（均值0，标准差1）"""
        s = series.copy()
        mean = s.mean()
        std = s.std()
        if std == 0 or pd.isna(std):
            return s.fillna(0.0) * 0.0  # 全部归零
        return (s - mean) / std

    @staticmethod
    def _compute_nonlinear_reversal(df: pd.DataFrame) -> pd.Series:
        """
        非线性反转因子

        只对极端涨跌幅(>±3%)施加反转信号，温和区间不惩罚。
        使用 tanh 平滑过渡，避免硬阈值：

            reversal = -tanh((pct_chg / 3.0)^2 * sign(pct_chg))

        效果：
        - |pct_chg| < 1%：反转信号接近 0
        - |pct_chg| = 3%：反转信号约 -0.78
        - |pct_chg| = 5%：反转信号接近 -1.0（饱和）
        """
        pct = pd.to_numeric(df["pct_chg"], errors="coerce").fillna(0.0)
        # 以 3% 为中心点
        scaled = (pct / 3.0)
        # 平方保留符号方向
        signal = np.tanh(scaled ** 2 * np.sign(scaled))
        return pd.Series(signal, index=df.index)

    @staticmethod
    def _compute_cluster_momentum(
        df: pd.DataFrame,
        cluster_labels: np.ndarray | None,
    ) -> pd.Series:
        """板块动量因子：同簇平均涨跌幅"""
        if cluster_labels is None or "pct_chg" not in df.columns:
            return pd.Series(0.0, index=df.index)

        pct = pd.to_numeric(df["pct_chg"], errors="coerce").fillna(0.0).values
        cluster_avg = np.zeros(len(df))

        for label in set(cluster_labels):
            if label == -1:
                continue
            mask = cluster_labels == label
            avg = pct[mask].mean()
            cluster_avg[mask] = avg

        # 噪声点用全市场均值
        noise_mask = cluster_labels == -1
        if noise_mask.any():
            cluster_avg[noise_mask] = pct.mean()

        return pd.Series(cluster_avg, index=df.index)

    def _orthogonalize_groups(self, factors: pd.DataFrame) -> pd.DataFrame:
        """
        施密特正交化：对同组因子进行正交化，消除共线性

        例如 PE 和 PB 同属 "valuation" 组：
        - 保留 PE 不变
        - PB' = PB - proj(PB, PE)  （减去 PB 在 PE 方向的投影）

        效果：正交化后的 PB' 只包含 PB 独有的信息，不与 PE 重叠
        """
        result = factors.copy()

        # 收集各组的因子
        groups: dict[str, list[str]] = {}
        for fdef in FACTOR_DEFS:
            if fdef.name in result.columns and fdef.group:
                groups.setdefault(fdef.group, []).append(fdef.name)

        for group_name, factor_names in groups.items():
            if len(factor_names) <= 1:
                continue

            # 施密特正交化
            orthogonal_vectors = []
            for i, fname in enumerate(factor_names):
                v = result[fname].fillna(0.0).values.copy().astype(float)
                for prev_v in orthogonal_vectors:
                    # 投影并减去
                    dot_product = np.dot(v, prev_v)
                    norm_sq = np.dot(prev_v, prev_v)
                    if norm_sq > 1e-10:
                        v -= (dot_product / norm_sq) * prev_v
                orthogonal_vectors.append(v)
                result[fname] = v

            logger.debug(
                f"正交化组 '{group_name}': {factor_names}"
            )

        return result

    def _get_weights(self) -> dict[str, float]:
        """获取因子权重：优先 ICIR 自适应，fallback 到默认值"""
        if self._icir_weights is not None:
            # 使用 ICIR 权重，补充缺失的因子用默认值
            weights = {}
            for fdef in FACTOR_DEFS:
                if fdef.name in self._icir_weights:
                    weights[fdef.name] = self._icir_weights[fdef.name]
                else:
                    weights[fdef.name] = fdef.default_weight
            return weights
        else:
            # 全部用默认值
            return {fdef.name: fdef.default_weight for fdef in FACTOR_DEFS}
