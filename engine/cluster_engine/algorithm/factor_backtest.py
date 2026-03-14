"""
因子 IC 回测框架 v1.0

职责：
  1. 利用 DuckDB 中已有的历史快照数据（stock_snapshot_daily）计算因子 RankIC
  2. 通过 AKShare 补充拉取不足的历史数据
  3. 计算滚动 ICIR（IC 均值 / IC 标准差）作为自适应因子权重
  4. 输出因子诊断报告

核心概念：
  - RankIC (Rank Information Coefficient):
    因子截面排名与次日收益排名的 Spearman 相关系数
    IC > 0 表示因子方向正确，|IC| > 0.03 通常认为有效
    
  - ICIR (IC Information Ratio):
    IC 均值 / IC 标准差，衡量因子预测力的稳定性
    |ICIR| > 0.5 是好因子的标准

  - 滚动窗口：使用最近 N 天的 IC 值计算 ICIR
"""

import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from loguru import logger
from scipy import stats

from .predictor_v2 import FACTOR_DEFS, StockPredictorV2


@dataclass
class FactorICReport:
    """单因子 IC 回测报告"""
    factor_name: str
    ic_mean: float = 0.0          # IC 均值
    ic_std: float = 0.0           # IC 标准差
    icir: float = 0.0             # IC IR = mean / std
    ic_positive_rate: float = 0.0  # IC 为正的比率
    ic_series: list[float] = field(default_factory=list)  # 每日 IC 值
    ic_dates: list[str] = field(default_factory=list)      # 对应日期
    t_stat: float = 0.0           # t 统计量
    p_value: float = 1.0          # 显著性


@dataclass
class BacktestResult:
    """回测结果汇总"""
    factor_reports: dict[str, FactorICReport] = field(default_factory=dict)
    icir_weights: dict[str, float] = field(default_factory=dict)
    backtest_days: int = 0
    total_stocks_avg: int = 0
    computation_time_ms: float = 0
    data_source: str = ""  # "local" or "remote"


class FactorBacktester:
    """
    因子 IC 回测器

    使用流程：
    1. 加载历史截面数据（从 DuckDB 或远程拉取）
    2. 对每个因子、每个交易日，计算截面 RankIC
    3. 滚动计算 ICIR 作为自适应权重
    4. 将权重注入 StockPredictorV2
    """

    def __init__(self, rolling_window: int = 20):
        """
        Args:
            rolling_window: ICIR 滚动窗口天数（默认 20 个交易日 ≈ 1 个月）
        """
        self.rolling_window = rolling_window
        self._predictor_helper = StockPredictorV2()

    def run_backtest(
        self,
        daily_snapshots: dict[str, pd.DataFrame],
    ) -> BacktestResult:
        """
        执行因子 IC 回测

        Args:
            daily_snapshots: { date_str: snapshot_df } 按日期排序的全市场快照
                            每个 df 必须包含 code, pct_chg 等因子列

        Returns:
            BacktestResult
        """
        t0 = time.time()

        dates = sorted(daily_snapshots.keys())
        if len(dates) < 3:
            logger.warning(f"回测数据不足: 仅 {len(dates)} 天，至少需要 3 天")
            return BacktestResult(backtest_days=len(dates))

        logger.info(f"📊 因子 IC 回测启动: {dates[0]} ~ {dates[-1]} ({len(dates)} 天)")

        # 为每个因子收集 IC 时序
        factor_ic_series: dict[str, list[tuple[str, float]]] = {
            fdef.name: [] for fdef in FACTOR_DEFS
        }

        total_stocks = 0

        # 遍历每对相邻交易日
        for i in range(len(dates) - 1):
            today = dates[i]
            tomorrow = dates[i + 1]

            snap_today = daily_snapshots[today]
            snap_tomorrow = daily_snapshots[tomorrow]

            if snap_today.empty or snap_tomorrow.empty:
                continue
            if len(snap_today) < 50 or len(snap_tomorrow) < 50:
                continue

            # 计算次日收益
            next_day_returns = self._compute_next_day_returns(
                snap_today, snap_tomorrow
            )
            if next_day_returns is None or len(next_day_returns) < 50:
                continue

            total_stocks += len(next_day_returns)

            # 对每个因子计算截面 RankIC
            for fdef in FACTOR_DEFS:
                ic = self._compute_single_factor_ic(
                    snap_today, next_day_returns, fdef
                )
                if ic is not None:
                    factor_ic_series[fdef.name].append((today, ic))

        # 汇总计算
        factor_reports = {}
        icir_weights = {}

        for fdef in FACTOR_DEFS:
            series = factor_ic_series[fdef.name]
            if len(series) < 3:
                logger.debug(f"因子 {fdef.name}: IC 数据不足 ({len(series)} 天)，跳过")
                continue

            ic_values = [v for _, v in series]
            ic_dates = [d for d, _ in series]

            ic_arr = np.array(ic_values)
            ic_mean = float(np.mean(ic_arr))
            ic_std = float(np.std(ic_arr, ddof=1)) if len(ic_arr) > 1 else 1.0

            # ICIR
            icir = ic_mean / ic_std if ic_std > 1e-10 else 0.0

            # t 检验
            if len(ic_arr) > 2:
                t_stat, p_value = stats.ttest_1samp(ic_arr, 0)
                t_stat = float(t_stat)
                p_value = float(p_value)
            else:
                t_stat, p_value = 0.0, 1.0

            # 正 IC 比率
            ic_positive_rate = float(np.mean(ic_arr > 0))

            report = FactorICReport(
                factor_name=fdef.name,
                ic_mean=round(ic_mean, 6),
                ic_std=round(ic_std, 6),
                icir=round(icir, 4),
                ic_positive_rate=round(ic_positive_rate, 4),
                ic_series=ic_values,
                ic_dates=ic_dates,
                t_stat=round(t_stat, 4),
                p_value=round(p_value, 6),
            )
            factor_reports[fdef.name] = report

            # 如果使用滚动窗口，用最近 N 天的 IC 计算 ICIR
            window = min(self.rolling_window, len(ic_arr))
            recent_ic = ic_arr[-window:]
            recent_mean = float(np.mean(recent_ic))
            recent_std = float(np.std(recent_ic, ddof=1)) if len(recent_ic) > 1 else 1.0
            rolling_icir = recent_mean / recent_std if recent_std > 1e-10 else 0.0

            # ICIR 权重 = 方向 × |ICIR|（方向由因子定义控制）
            # 这里 ICIR 本身已经包含了方向信息（因为 IC 的符号反映了因子与收益的关系）
            icir_weights[fdef.name] = round(rolling_icir, 4)

        # 归一化权重（让绝对值之和为 1）
        icir_weights = self._normalize_weights(icir_weights)

        avg_stocks = int(total_stocks / max(len(dates) - 1, 1))
        elapsed = (time.time() - t0) * 1000

        result = BacktestResult(
            factor_reports=factor_reports,
            icir_weights=icir_weights,
            backtest_days=len(dates),
            total_stocks_avg=avg_stocks,
            computation_time_ms=elapsed,
        )

        # 打印汇总
        logger.info(f"📊 因子 IC 回测完成: {len(dates)} 天, 平均 {avg_stocks} 只/天, 耗时 {elapsed:.0f}ms")
        logger.info("─" * 60)
        logger.info(f"{'因子':<20} {'IC均值':>8} {'IC标准差':>8} {'ICIR':>8} {'IC>0%':>7} {'权重':>8}")
        logger.info("─" * 60)
        for fdef in FACTOR_DEFS:
            if fdef.name in factor_reports:
                r = factor_reports[fdef.name]
                w = icir_weights.get(fdef.name, 0.0)
                logger.info(
                    f"{fdef.name:<20} {r.ic_mean:>8.4f} {r.ic_std:>8.4f} "
                    f"{r.icir:>8.4f} {r.ic_positive_rate:>6.1%} {w:>8.4f}"
                )
        logger.info("─" * 60)

        return result

    def _compute_next_day_returns(
        self,
        snap_today: pd.DataFrame,
        snap_tomorrow: pd.DataFrame,
    ) -> pd.Series | None:
        """计算次日收益率（用明天的 pct_chg）"""
        if "code" not in snap_tomorrow.columns or "pct_chg" not in snap_tomorrow.columns:
            return None

        tomorrow_returns = snap_tomorrow.set_index(
            snap_tomorrow["code"].astype(str)
        )["pct_chg"]
        tomorrow_returns = pd.to_numeric(tomorrow_returns, errors="coerce")

        # 只保留今天也有的股票
        today_codes = set(snap_today["code"].astype(str).tolist())
        common_codes = today_codes & set(tomorrow_returns.index)

        if len(common_codes) < 50:
            return None

        return tomorrow_returns.loc[list(common_codes)]

    def _compute_single_factor_ic(
        self,
        snap_today: pd.DataFrame,
        next_day_returns: pd.Series,
        fdef: "FactorDef",
    ) -> float | None:
        """
        计算单因子截面 RankIC

        RankIC = Spearman(factor_rank, return_rank)
        """
        df = snap_today.copy()
        df["_code"] = df["code"].astype(str)

        # 提取因子值
        if fdef.name == "cluster_momentum":
            # 板块动量需要聚类信息，在回测中简化为直接用行业/板块
            # 这里用 pct_chg 的行业均值作为近似
            return None  # 板块动量因子在回测中跳过（需要聚类信息）

        elif fdef.name == "reversal":
            factor_values = self._predictor_helper._compute_nonlinear_reversal(df)
            factor_values.index = df["_code"].values
        else:
            if fdef.source_col not in df.columns:
                return None
            factor_values = pd.to_numeric(
                df[fdef.source_col], errors="coerce"
            )
            factor_values.index = df["_code"].values

        # 对齐
        common = list(set(factor_values.dropna().index) & set(next_day_returns.dropna().index))
        if len(common) < 50:
            return None

        f = factor_values.loc[common]
        r = next_day_returns.loc[common]

        # Spearman RankIC
        try:
            ic, _ = stats.spearmanr(f.values, r.values)
            if np.isnan(ic):
                return None
            return float(ic)
        except Exception:
            return None

    @staticmethod
    def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
        """
        归一化 ICIR 权重

        策略：
        1. 保留方向（ICIR 的符号）
        2. 绝对值之和归一化到 1.0
        3. 过滤掉 |ICIR| < 0.1 的因子（噪声）
        """
        # 过滤噪声因子
        filtered = {k: v for k, v in weights.items() if abs(v) >= 0.1}

        if not filtered:
            # 如果全被过滤了，放宽到 0.05
            filtered = {k: v for k, v in weights.items() if abs(v) >= 0.05}

        if not filtered:
            # 还是空，回退到默认权重
            logger.warning("ICIR 权重全部不显著，回退到默认权重")
            return {fdef.name: fdef.default_weight for fdef in FACTOR_DEFS}

        total = sum(abs(v) for v in filtered.values())
        if total < 1e-10:
            return filtered

        normalized = {k: round(v / total, 4) for k, v in filtered.items()}
        return normalized


def run_ic_backtest_from_store(
    store: "DuckDBStore",
    rolling_window: int = 20,
) -> BacktestResult:
    """
    便捷函数：直接从 DuckDB 存储中读取历史快照并执行回测

    Args:
        store: DuckDB 存储实例
        rolling_window: ICIR 滚动窗口

    Returns:
        BacktestResult
    """
    # 获取所有可用的历史快照日期
    dates = store.get_snapshot_daily_dates()

    if len(dates) < 3:
        logger.warning(
            f"DuckDB 中仅有 {len(dates)} 天快照数据，"
            f"建议先运行 compute 积累更多历史数据"
        )
        return BacktestResult(backtest_days=len(dates), data_source="local_insufficient")

    # 读取所有快照
    daily_snapshots = {}
    for d in dates:
        snap = store.get_snapshot_daily(d)
        if not snap.empty:
            daily_snapshots[d] = snap

    logger.info(f"📦 从 DuckDB 加载 {len(daily_snapshots)} 天历史快照")

    backtester = FactorBacktester(rolling_window=rolling_window)
    result = backtester.run_backtest(daily_snapshots)
    result.data_source = "local"
    return result
