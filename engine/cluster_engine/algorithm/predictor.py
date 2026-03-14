"""
预测模块 v1.0 — 明日上涨概率估计

方法：多因子截面评分模型（无需历史训练数据）

原理：
  基于量化研究公认的短期有效因子，对当日全市场股票进行截面打分，
  将多因子得分通过 Sigmoid 映射为 [0, 1] 的上涨概率估计值。

因子体系：
  1. 动量反转因子 (pct_chg)      — 当日涨跌幅，短期存在反转效应
  2. 换手率因子 (turnover_rate)   — 换手率极端值信号
  3. 成交额因子 (amount)          — 资金活跃度
  4. 估值因子 (pe_ttm, pb)       — 低估值溢价
  5. 市值因子 (total_mv)         — 小市值效应
  6. 板块动量因子 (cluster_avg)   — 同簇股票平均表现

风险提示：
  本模型仅供学习研究，不构成任何投资建议。
  股票市场存在极高不确定性，历史因子规律不代表未来收益。
"""

import numpy as np
import pandas as pd
from loguru import logger
from dataclasses import dataclass, field


@dataclass
class PredictionResult:
    """预测结果"""
    # { code: probability }
    predictions: dict[str, float] = field(default_factory=dict)
    # 因子明细 { code: { factor_name: score } }
    factor_details: dict[str, dict[str, float]] = field(default_factory=dict)
    # 全市场统计
    avg_probability: float = 0.0
    bullish_count: int = 0      # 概率 > 0.5
    bearish_count: int = 0      # 概率 < 0.5
    total_count: int = 0
    computation_time_ms: float = 0


class StockPredictor:
    """
    多因子截面评分预测器

    对全市场股票基于当日截面数据计算「明日上涨概率」。
    使用分位数排名（cross-sectional rank）消除量纲差异，
    再通过加权 Sigmoid 映射为概率。
    """

    # 因子权重（正值=该因子越高越看涨，负值=越高越看跌）
    FACTOR_WEIGHTS = {
        "reversal":       -0.25,   # 反转因子：今日涨幅大→明日可能回调
        "turnover_mean":  -0.10,   # 换手偏高→短期可能回落
        "amount_rank":     0.10,   # 成交额活跃→关注度高，正面
        "pe_value":       -0.15,   # 低 PE 更具上涨潜力（负向：PE越高得分越低）
        "pb_value":       -0.10,   # 低 PB 同理
        "size_effect":    -0.10,   # 小市值效应（市值越小可能越活跃）
        "cluster_momentum": 0.20,  # 板块动量：同簇平均涨幅正→联动上涨
    }

    def predict(
        self,
        snapshot_df: pd.DataFrame,
        cluster_labels: np.ndarray | None = None,
    ) -> PredictionResult:
        """
        计算全市场明日上涨概率

        Args:
            snapshot_df: 实时行情快照（必须包含 code, pct_chg 等字段）
            cluster_labels: HDBSCAN 聚类标签数组，与 snapshot_df 行对齐

        Returns:
            PredictionResult
        """
        import time
        t0 = time.time()

        if snapshot_df.empty or len(snapshot_df) < 50:
            logger.warning("快照数据不足，无法进行预测")
            return PredictionResult()

        df = snapshot_df.copy()

        # 确保必要列存在
        required = ["code", "pct_chg"]
        for col in required:
            if col not in df.columns:
                logger.error(f"快照缺少必要列: {col}")
                return PredictionResult()

        # ─── 1. 计算各因子的截面分位数排名 (0~1) ──────
        factor_scores = pd.DataFrame(index=df.index)

        # 因子 1: 反转因子（当日涨跌幅的排名）
        if "pct_chg" in df.columns:
            pct = pd.to_numeric(df["pct_chg"], errors="coerce").fillna(0)
            factor_scores["reversal"] = self._rank_normalize(pct)

        # 因子 2: 换手率因子
        if "turnover_rate" in df.columns:
            tr = pd.to_numeric(df["turnover_rate"], errors="coerce").fillna(0)
            factor_scores["turnover_mean"] = self._rank_normalize(tr)
        else:
            factor_scores["turnover_mean"] = 0.5

        # 因子 3: 成交额排名
        if "amount" in df.columns:
            amt = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
            factor_scores["amount_rank"] = self._rank_normalize(amt)
        else:
            factor_scores["amount_rank"] = 0.5

        # 因子 4: PE 估值因子
        if "pe_ttm" in df.columns:
            pe = pd.to_numeric(df["pe_ttm"], errors="coerce").fillna(0)
            # 过滤异常 PE（负值或极大值）
            pe = pe.clip(lower=0, upper=300)
            pe[pe == 0] = np.nan
            factor_scores["pe_value"] = self._rank_normalize(pe)
        else:
            factor_scores["pe_value"] = 0.5

        # 因子 5: PB 估值因子
        if "pb" in df.columns:
            pb = pd.to_numeric(df["pb"], errors="coerce").fillna(0)
            pb = pb.clip(lower=0, upper=50)
            pb[pb == 0] = np.nan
            factor_scores["pb_value"] = self._rank_normalize(pb)
        else:
            factor_scores["pb_value"] = 0.5

        # 因子 6: 市值因子（对数市值的排名）
        if "total_mv" in df.columns:
            mv = pd.to_numeric(df["total_mv"], errors="coerce").fillna(0)
            mv = np.log1p(mv.clip(lower=0))
            factor_scores["size_effect"] = self._rank_normalize(mv)
        else:
            factor_scores["size_effect"] = 0.5

        # 因子 7: 板块动量因子（同簇平均涨跌幅）
        if cluster_labels is not None and "pct_chg" in df.columns:
            pct = pd.to_numeric(df["pct_chg"], errors="coerce").fillna(0).values
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
            factor_scores["cluster_momentum"] = self._rank_normalize(
                pd.Series(cluster_avg, index=df.index)
            )
        else:
            factor_scores["cluster_momentum"] = 0.5

        # ─── 2. 加权合成综合得分 ─────────────────────
        composite = np.zeros(len(df))
        for factor_name, weight in self.FACTOR_WEIGHTS.items():
            if factor_name in factor_scores.columns:
                vals = factor_scores[factor_name].fillna(0.5).values
                composite += weight * (vals - 0.5)  # 中心化后加权

        # ─── 3. Sigmoid 映射为概率 ───────────────────
        # 调整灵敏度：乘以缩放系数让概率分布更合理
        SENSITIVITY = 6.0
        probabilities = 1.0 / (1.0 + np.exp(-SENSITIVITY * composite))

        # 轻微收缩到 [0.15, 0.85]，避免过于极端的预测
        probabilities = probabilities * 0.7 + 0.15

        # ─── 4. 组装结果 ────────────────────────────
        predictions = {}
        factor_detail = {}
        codes = df["code"].astype(str).values

        for i, code in enumerate(codes):
            prob = float(round(probabilities[i], 4))
            predictions[code] = prob

            # 因子明细
            detail = {}
            for factor_name in self.FACTOR_WEIGHTS:
                if factor_name in factor_scores.columns:
                    detail[factor_name] = float(
                        round(factor_scores[factor_name].iloc[i], 4)
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
        )

        logger.info(
            f"🔮 预测完成: {result.total_count} 只股票, "
            f"看涨 {result.bullish_count} / 看跌 {result.bearish_count}, "
            f"平均概率 {result.avg_probability:.2%}, "
            f"耗时 {elapsed:.0f}ms"
        )

        return result

    @staticmethod
    def _rank_normalize(series: pd.Series) -> pd.Series:
        """
        分位数排名归一化到 [0, 1]

        处理 NaN：NaN 给予中位排名 0.5
        """
        ranked = series.rank(pct=True, na_option="keep")
        return ranked.fillna(0.5)
