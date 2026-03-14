"""数据获取层 — 从各引擎收集 Agent 所需数据

独立文件便于扩展（Phase 2 加入 InfoEngine 数据源）。
"""

import asyncio
import datetime

from loguru import logger


class DataFetcher:
    """从各引擎收集 Agent 所需数据

    Phase 1 MVP: 直接调用引擎 Python 接口。
    Phase 2+: 通过 MCP Tool 调用。
    """

    def get_stock_data(self, target: str) -> dict:
        """获取基本面数据（DataEngine + ClusterEngine）"""
        try:
            from data_engine import get_data_engine
            de = get_data_engine()

            info = de.get_profile(target) or {}
            snapshot = de.get_snapshot()
            stock_row = {}
            if not snapshot.empty and "code" in snapshot.columns:
                match = snapshot[snapshot["code"] == target]
                if not match.empty:
                    stock_row = match.iloc[0].to_dict()

            return {**info, **stock_row}
        except Exception as e:
            logger.warning(f"获取基本面数据失败 [{target}]: {e}")
            return {}

    def get_quant_data(self, target: str) -> dict:
        """获取量化数据（QuantEngine）"""
        try:
            from quant_engine import get_quant_engine
            from data_engine import get_data_engine

            de = get_data_engine()
            end = datetime.date.today().strftime("%Y-%m-%d")
            start = (datetime.date.today() - datetime.timedelta(days=90)).strftime("%Y-%m-%d")
            daily = de.get_daily_history(target, start, end)

            qe = get_quant_engine()
            indicators = qe.compute_indicators(daily) if not daily.empty else {}

            # 因子权重信息
            weights, weight_source = qe.get_factor_weights()
            factor_defs = [
                {"name": f.name, "direction": f.direction, "weight": weights.get(f.name, f.default_weight)}
                for f in qe.get_factor_defs()
            ]

            return {**indicators, "factor_defs": factor_defs, "weight_source": weight_source}
        except Exception as e:
            logger.warning(f"获取量化数据失败 [{target}]: {e}")
            return {}

    def get_info_data(self, target: str) -> dict:
        """获取消息面数据 — Phase 1 返回空（InfoEngine 在 Phase 2 实现）"""
        return {"news": [], "announcements": [], "note": "InfoEngine 尚未实现，消息面数据为空"}

    async def fetch_all(self, target: str) -> dict[str, dict]:
        """异步获取所有引擎数据（避免阻塞事件循环）"""
        fund_data, info_data, quant_data = await asyncio.gather(
            asyncio.to_thread(self.get_stock_data, target),
            asyncio.to_thread(self.get_info_data, target),
            asyncio.to_thread(self.get_quant_data, target),
        )
        return {
            "fundamental": fund_data,
            "info": info_data,
            "quant": quant_data,
        }
