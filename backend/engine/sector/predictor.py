"""板块级多因子预测 + 轮动预测模型

与 StockPredictorV2 同架构：MAD去极值 → Z-Score → 正交化 → 加权 → 正态CDF
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats
from loguru import logger


@dataclass
class SectorFactorDef:
    name: str
    direction: int          # +1=因子越大越看涨, -1=因子越大越看跌
    group: str = ""
    default_weight: float = 0.0
    desc: str = ""


SECTOR_FACTOR_DEFS: list[SectorFactorDef] = [
    SectorFactorDef("sector_reversal_1d",       -1, group="momentum",     default_weight=-0.12, desc="昨日涨幅极端→今日反转"),
    SectorFactorDef("sector_momentum_5d",        +1, group="momentum",     default_weight=0.10,  desc="5日板块涨幅动量"),
    SectorFactorDef("sector_momentum_20d",       +1, group="momentum",     default_weight=0.08,  desc="20日板块动量"),
    SectorFactorDef("sector_volume_surge",       +1, group="liquidity",    default_weight=0.06,  desc="成交量/20日均量比值"),
    SectorFactorDef("sector_turnover_zscore",    -1, group="liquidity",    default_weight=-0.05, desc="换手率Z-Score（过高→回落）"),
    SectorFactorDef("main_force_flow_ratio",     +1, group="capital_flow", default_weight=0.15,  desc="当日主力净流入占比"),
    SectorFactorDef("main_force_flow_5d_avg",    +1, group="capital_flow", default_weight=0.15,  desc="5日主力净流入均值"),
    SectorFactorDef("main_force_flow_trend",     +1, group="capital_flow", default_weight=0.12,  desc="连续净流入天数(+N/-N)"),
    SectorFactorDef("super_large_flow_ratio",    +1, group="capital_flow", default_weight=0.10,  desc="超大单净流入占比"),
    SectorFactorDef("sector_ma_dev_10",          -1, group="technical",    default_weight=-0.07, desc="10日均线偏离度"),
]


@dataclass
class SectorPredictionResult:
    predictions: dict[str, float] = field(default_factory=dict)        # { board_code: probability }
    factor_details: dict[str, dict[str, float]] = field(default_factory=dict)
    signals: dict[str, str] = field(default_factory=dict)              # { board_code: signal }
    computation_time_ms: float = 0


class SectorPredictor:
    """板块级多因子预测器"""

    def __init__(self, factor_defs: list[SectorFactorDef] | None = None):
        self.factor_defs = factor_defs or SECTOR_FACTOR_DEFS

    def predict(
        self,
        board_daily_df: pd.DataFrame,
        fund_flow_df: pd.DataFrame,
    ) -> SectorPredictionResult:
        """
        执行板块预测

        参数:
            board_daily_df: sector.board_daily 数据，需含多日历史
            fund_flow_df: sector.fund_flow_daily 数据，需含多日历史
        """
        t0 = time.monotonic()

        if board_daily_df.empty:
            logger.warning("SectorPredictor: 无板块行情数据，跳过预测")
            return SectorPredictionResult()

        # 1. 计算因子矩阵
        factor_matrix = self._compute_factors(board_daily_df, fund_flow_df)
        if factor_matrix.empty:
            return SectorPredictionResult()

        # 2. MAD 去极值 + Z-Score 标准化
        factor_cols = [f.name for f in self.factor_defs if f.name in factor_matrix.columns]
        for col in factor_cols:
            factor_matrix[col] = self._mad_winsorize(factor_matrix[col])
            factor_matrix[col] = self._zscore(factor_matrix[col])

        # 3. 施密特正交化（同组因子）
        factor_matrix = self._orthogonalize(factor_matrix)

        # 4. 应用因子方向
        for fdef in self.factor_defs:
            if fdef.name in factor_matrix.columns:
                factor_matrix[fdef.name] *= fdef.direction

        # 5. 加权合成
        weights = {f.name: f.default_weight for f in self.factor_defs}
        weight_arr = np.array([weights[c] for c in factor_cols])
        vals = factor_matrix[factor_cols].fillna(0).values
        composite = vals @ weight_arr

        # 6. 归一化 composite → 正态 CDF → 概率
        std = np.std(composite)
        if std > 0:
            composite = (composite - np.mean(composite)) / std
        probabilities = stats.norm.cdf(composite)
        # 收缩到 [0.12, 0.88]
        probabilities = 0.12 + probabilities * 0.76

        # 7. 组装结果
        predictions: dict[str, float] = {}
        signals: dict[str, str] = {}
        factor_details_map: dict[str, dict[str, float]] = {}
        codes = factor_matrix["board_code"].tolist()

        for i, code in enumerate(codes):
            prob = float(probabilities[i])
            predictions[code] = prob
            if prob > 0.6:
                signals[code] = "bullish"
            elif prob < 0.4:
                signals[code] = "bearish"
            else:
                signals[code] = "neutral"
            factor_details_map[code] = {
                col: float(factor_matrix.iloc[i][col])
                for col in factor_cols
                if col in factor_matrix.columns
            }

        elapsed = (time.monotonic() - t0) * 1000
        logger.info(
            f"⏱️ SectorPredictor.predict 耗时 {elapsed:.0f}ms, "
            f"{len(predictions)} 个板块"
        )

        return SectorPredictionResult(
            predictions=predictions,
            factor_details=factor_details_map,
            signals=signals,
            computation_time_ms=elapsed,
        )

    def _compute_factors(
        self, board_df: pd.DataFrame, flow_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """从原始数据计算 10 个因子"""
        if "board_code" not in board_df.columns:
            return pd.DataFrame()

        results = []
        for code, group in board_df.groupby("board_code"):
            group = group.sort_values("date")
            if len(group) < 2:
                continue

            row: dict = {"board_code": code}
            latest = group.iloc[-1]

            # 1. sector_reversal_1d — 昨日涨跌幅
            row["sector_reversal_1d"] = float(latest.get("pct_chg", 0) or 0)

            # 2. sector_momentum_5d — 5日累计涨幅
            tail5 = group["pct_chg"].tail(5)
            row["sector_momentum_5d"] = float(tail5.sum())

            # 3. sector_momentum_20d — 20日累计涨幅
            tail20 = group["pct_chg"].tail(20)
            row["sector_momentum_20d"] = float(tail20.sum())

            # 4. sector_volume_surge — 成交量 / 20日均量
            if "volume" in group.columns and len(group) >= 20:
                avg_vol = group["volume"].tail(20).mean()
                cur_vol = float(latest.get("volume", 0) or 0)
                row["sector_volume_surge"] = cur_vol / avg_vol if avg_vol > 0 else 1.0
            else:
                row["sector_volume_surge"] = 1.0

            # 5. sector_turnover_zscore
            if "turnover_rate" in group.columns and len(group) >= 20:
                tr = group["turnover_rate"].tail(20)
                mean_tr = tr.mean()
                std_tr = tr.std()
                cur_tr = float(latest.get("turnover_rate", 0) or 0)
                row["sector_turnover_zscore"] = (cur_tr - mean_tr) / std_tr if std_tr > 0 else 0.0
            else:
                row["sector_turnover_zscore"] = 0.0

            # 10. sector_ma_dev_10 — 10日均线偏离
            if "close" in group.columns and len(group) >= 10:
                ma10 = group["close"].tail(10).mean()
                cur_close = float(latest.get("close", 0) or 0)
                row["sector_ma_dev_10"] = (cur_close - ma10) / ma10 * 100 if ma10 > 0 else 0.0
            else:
                row["sector_ma_dev_10"] = 0.0

            # 资金流因子（从 flow_df 取）
            self._fill_flow_factors(row, code, flow_df)

            results.append(row)

        return pd.DataFrame(results) if results else pd.DataFrame()

    @staticmethod
    def _fill_flow_factors(row: dict, code: str, flow_df: pd.DataFrame):
        """填充资金流相关因子"""
        defaults = {
            "main_force_flow_ratio": 0.0,
            "main_force_flow_5d_avg": 0.0,
            "main_force_flow_trend": 0.0,
            "super_large_flow_ratio": 0.0,
        }

        if flow_df.empty or "board_code" not in flow_df.columns:
            row.update(defaults)
            return

        code_flow = flow_df[flow_df["board_code"] == code].sort_values("date")
        if code_flow.empty:
            row.update(defaults)
            return

        fl = code_flow.iloc[-1]

        # 6. main_force_flow_ratio — 当日主力净流入占比
        row["main_force_flow_ratio"] = float(fl.get("main_force_net_ratio", 0) or 0)

        # 9. super_large_flow_ratio — 超大单占主力比
        super_large = float(fl.get("super_large_net_inflow", 0) or 0)
        main_total = float(fl.get("main_force_net_inflow", 0) or 0)
        row["super_large_flow_ratio"] = super_large / abs(main_total) if main_total else 0.0

        # 7. main_force_flow_5d_avg — 5日主力净流入均值
        tail = code_flow["main_force_net_inflow"].tail(5)
        row["main_force_flow_5d_avg"] = float(tail.mean())

        # 8. main_force_flow_trend — 连续流入天数
        flows = code_flow["main_force_net_inflow"].tolist()
        trend = 0
        for v in reversed(flows):
            if v > 0:
                if trend >= 0:
                    trend += 1
                else:
                    break
            elif v < 0:
                if trend <= 0:
                    trend -= 1
                else:
                    break
            else:
                break
        row["main_force_flow_trend"] = float(trend)

    @staticmethod
    def _mad_winsorize(series: pd.Series, n_mad: float = 5.0) -> pd.Series:
        """MAD 去极值"""
        median = series.median()
        mad = (series - median).abs().median()
        if mad == 0:
            return series
        upper = median + n_mad * mad
        lower = median - n_mad * mad
        return series.clip(lower, upper)

    @staticmethod
    def _zscore(series: pd.Series) -> pd.Series:
        """Z-Score 标准化"""
        std = series.std()
        if std == 0:
            return series * 0
        return (series - series.mean()) / std

    def _orthogonalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """施密特正交化（同组因子）"""
        groups: dict[str, list[str]] = {}
        for fdef in self.factor_defs:
            if fdef.name in df.columns:
                groups.setdefault(fdef.group, []).append(fdef.name)

        for group_name, cols in groups.items():
            if len(cols) < 2:
                continue
            for i in range(1, len(cols)):
                for j in range(i):
                    v_i = df[cols[i]].values.astype(float)
                    v_j = df[cols[j]].values.astype(float)
                    dot = np.dot(v_i, v_j)
                    norm = np.dot(v_j, v_j)
                    if norm > 0:
                        df[cols[i]] = v_i - (dot / norm) * v_j
        return df
