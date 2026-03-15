"""数据获取层 — 从各引擎收集 Agent 所需数据

独立文件便于扩展（Phase 2 加入 InfoEngine 数据源）。
"""

import asyncio
import datetime
import importlib
from typing import Any

import pandas as pd
from loguru import logger


SELF_DISPATCH: set[str] = {
    "get_financials", "get_money_flow", "get_northbound_holding",
    "get_margin_balance", "get_turnover_rate", "get_restrict_stock_unlock",
    "get_daily_history", "get_technical_indicators", "get_factor_scores",
}

ACTION_DISPATCH: dict[str, tuple[str, str, str, bool]] = {
    # action → (module_name, getter_fn, method_name, is_async)
    "get_stock_info":           ("data_engine",    "get_data_engine",    "get_profile",           False),
    "get_news":                 ("info_engine",    "get_info_engine",    "get_news",              True),
    "get_announcements":        ("info_engine",    "get_info_engine",    "get_announcements",     True),
    "get_cluster_for_stock":    ("cluster_engine", "get_cluster_engine", "get_cluster_for_stock", False),
}


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

    async def get_info_data(self, target: str) -> dict:
        """获取消息面数据（InfoEngine）"""
        try:
            from info_engine import get_info_engine
            ie = get_info_engine()
            news = await ie.get_news(target, limit=20)
            announcements = await ie.get_announcements(target, limit=10)
            return {
                "news": [n.model_dump() for n in news],
                "announcements": [a.model_dump() for a in announcements],
            }
        except Exception as e:
            logger.warning(f"获取消息面数据失败 [{target}]: {e}")
            return {"news": [], "announcements": [], "error": str(e)}

    async def fetch_all(self, target: str) -> dict[str, dict]:
        """异步获取所有引擎数据"""
        fund_data, info_data, quant_data = await asyncio.gather(
            asyncio.to_thread(self.get_stock_data, target),
            self.get_info_data(target),  # now async, no need for to_thread
            asyncio.to_thread(self.get_quant_data, target),
        )
        return {
            "fundamental": fund_data,
            "info": info_data,
            "quant": quant_data,
        }

    async def fetch_by_request(self, req) -> Any:
        """按 DataRequest 路由到对应引擎方法或 DataFetcher 自身方法"""
        import re
        # 如果 params.code 不是 6 位数字，尝试按名称解析
        if "code" in req.params and not re.fullmatch(r"\d{6}", str(req.params["code"]).strip()):
            resolved = self._resolve_code(req.params["code"])
            if resolved:
                req.params = {**req.params, "code": resolved}
            else:
                return {"error": f"无法解析股票代码: {req.params['code']}"}
        if req.action in ACTION_DISPATCH:
            module_name, getter_fn, method_name, is_async = ACTION_DISPATCH[req.action]
            mod = importlib.import_module(module_name)
            engine = getattr(mod, getter_fn)()
            method = getattr(engine, method_name)
            if is_async:
                return await method(**req.params)
            else:
                return await asyncio.to_thread(method, **req.params)
        elif req.action in SELF_DISPATCH:
            method = getattr(self, req.action)
            result = await asyncio.to_thread(method, **req.params)
            # 截断返回值，避免超出 LLM 上下文预算
            if isinstance(result, dict):
                return {k: str(v)[:300] if isinstance(v, str) else v for k, v in result.items()}
            return result
        else:
            raise ValueError(f"不支持的 action: {req.action}")

    def _resolve_code(self, name: str) -> str:
        """按名称模糊匹配股票代码，找不到返回空字符串"""
        try:
            from data_engine import get_data_engine
            profiles = get_data_engine().get_profiles()
            name_lower = name.lower()
            for code, info in profiles.items():
                stock_name = info.get("name", "")
                if stock_name and (stock_name in name or name_lower in stock_name.lower()):
                    return code
        except Exception as e:
            logger.warning(f"_resolve_code 失败: {e}")
        return ""

    def get_financials(self, code: str) -> dict:
        """获取最新一期财报关键指标"""
        try:
            import akshare as ak
            df = ak.stock_financial_analysis_indicator(symbol=code, start_year="2020")
            if df is None or df.empty:
                return {"error": f"无财务数据: {code}"}
            row = df.iloc[-1]
            result: dict = {"code": code, "report_date": str(row.get("日期", ""))}
            KEY_COLS = {
                "摊薄每股收益(元)": "每股收益",
                "每股净资产_调整后(元)": "每股净资产",
                "净资产收益率(%)": "净资产收益率(%)",
                "总资产净利润率(%)": "总资产净利率(%)",
                "营业利润率(%)": "营业利润率(%)",
                "销售净利率(%)": "销售净利率(%)",
                "资产负债率(%)": "资产负债率(%)",
                "流动比率": "流动比率",
                "主营业务收入增长率(%)": "营收增长率(%)",
                "净利润增长率(%)": "净利润增长率(%)",
            }
            for col, label in KEY_COLS.items():
                if col in row.index and pd.notna(row[col]):
                    result[label] = str(row[col])
            return result
        except Exception as e:
            logger.warning(f"get_financials 失败 [{code}]: {e}")
            return {"error": str(e)}

    def get_money_flow(self, code: str) -> dict:
        """获取当日资金流向"""
        try:
            import akshare as ak
            market = "sh" if code.startswith("6") else "sz"
            df = ak.stock_individual_fund_flow(stock=code, market=market)
            if df is None or df.empty:
                return {"error": f"无资金流向数据: {code}"}
            row = df.iloc[-1]
            return {
                "code": code,
                "date": str(row.get("日期", "")),
                "主力净流入": str(row.get("主力净流入-净额", "")),
                "主力净流入占比": str(row.get("主力净流入-净占比", "")),
                "超大单净流入": str(row.get("超大单净流入-净额", "")),
                "大单净流入": str(row.get("大单净流入-净额", "")),
                "小单净流入": str(row.get("小单净流入-净额", "")),
            }
        except Exception as e:
            logger.warning(f"get_money_flow 失败 [{code}]: {e}")
            return {"error": str(e)}

    def get_daily_history(self, code: str, days: int = 60) -> dict:
        """获取日线行情（最近 N 天）"""
        try:
            import datetime
            from data_engine import get_data_engine
            de = get_data_engine()
            end = datetime.date.today().strftime("%Y-%m-%d")
            start = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
            df = de.get_daily_history(code, start, end)
            if not isinstance(df, pd.DataFrame) or df.empty:
                return {"error": f"无日线数据: {code}"}
            rows = df.tail(10).to_dict(orient="records")
            return {"code": code, "days": len(df), "recent": rows}
        except Exception as e:
            logger.warning(f"get_daily_history 失败 [{code}]: {e}")
            return {"error": str(e)}

    def get_technical_indicators(self, code: str, days: int = 60) -> dict:
        """获取技术指标（RSI/MACD/布林带）"""
        try:
            import datetime
            from data_engine import get_data_engine
            from quant_engine import get_quant_engine
            de = get_data_engine()
            end = datetime.date.today().strftime("%Y-%m-%d")
            start = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
            df = de.get_daily_history(code, start, end)
            if not isinstance(df, pd.DataFrame) or df.empty:
                return {"error": f"无日线数据: {code}"}
            qe = get_quant_engine()
            indicators = qe.compute_indicators(df)
            return {"code": code, **indicators}
        except Exception as e:
            logger.warning(f"get_technical_indicators 失败 [{code}]: {e}")
            return {"error": str(e)}

    def get_factor_scores(self, code: str) -> dict:
        """获取多因子评分"""
        try:
            import datetime
            from data_engine import get_data_engine
            from quant_engine import get_quant_engine
            de = get_data_engine()
            end = datetime.date.today().strftime("%Y-%m-%d")
            start = (datetime.date.today() - datetime.timedelta(days=90)).strftime("%Y-%m-%d")
            df = de.get_daily_history(code, start, end)
            if not isinstance(df, pd.DataFrame) or df.empty:
                return {"error": f"无日线数据: {code}"}
            qe = get_quant_engine()
            result = qe.predict(code, df)
            weights, weight_source = qe.get_factor_weights()
            factor_defs = [
                {"name": f.name, "direction": f.direction, "weight": weights.get(f.name, f.default_weight)}
                for f in qe.get_factor_defs()
            ]
            return {
                "code": code,
                "signal": result.signal,
                "score": result.score,
                "confidence": result.confidence,
                "factor_defs": factor_defs,
                "weight_source": weight_source,
            }
        except Exception as e:
            logger.warning(f"get_factor_scores 失败 [{code}]: {e}")
            return {"error": str(e)}

    def get_northbound_holding(self, code: str) -> dict:
        """获取北向持股数据"""
        try:
            import akshare as ak
            df = ak.stock_hsgt_individual_em(symbol=code)
            if df is None or df.empty:
                return {"error": f"无北向持股数据: {code}"}
            row = df.iloc[-1]
            return {
                "code": code,
                "date": str(row.get("日期", "")),
                "持股数量": str(row.get("持股数量", "")),
                "持股市值": str(row.get("持股市值", "")),
                "持股占比": str(row.get("持股占A股百分比", "")),
                "持股变化": str(row.get("持股变化数量", "")),
            }
        except Exception as e:
            logger.warning(f"get_northbound_holding 失败 [{code}]: {e}")
            return {"error": str(e)}

    def get_margin_balance(self, code: str) -> dict:
        """获取融资融券余额（按交易所路由：6xxxxx=上交所，其余=深交所）"""
        try:
            import akshare as ak
            if code.startswith("6"):
                df = ak.stock_margin_detail_sse(symbol=code)
            else:
                df = ak.stock_margin_detail_szse(symbol=code)
            if df is None or df.empty:
                return {"error": f"无融资融券数据: {code}"}
            row = df.iloc[-1]
            return {
                "code": code,
                "date": str(row.iloc[0]),
                "融资余额": str(row.get("融资余额", "")),
                "融券余量": str(row.get("融券余量", "")),
            }
        except Exception as e:
            logger.warning(f"get_margin_balance 失败 [{code}]: {e}")
            return {"error": str(e)}

    def get_turnover_rate(self, code: str) -> dict:
        """从 DataEngine snapshot 获取换手率"""
        try:
            from data_engine import get_data_engine
            snapshot = get_data_engine().get_snapshot()
            row = snapshot[snapshot["code"] == code]
            if row.empty:
                return {"error": f"未找到 {code}"}
            return {"code": code, "turnover_rate": float(row.iloc[0]["turnover_rate"])}
        except Exception as e:
            logger.warning(f"get_turnover_rate 失败 [{code}]: {e}")
            return {"error": str(e)}

    def get_restrict_stock_unlock(self, code: str) -> dict:
        """获取限售股解禁计划（最近 3 条）"""
        try:
            import akshare as ak
            df = ak.stock_restricted_release_detail_em(symbol=code)
            if df is None or df.empty:
                return {"code": code, "unlocks": []}
            unlocks = []
            for _, r in df.head(3).iterrows():
                unlocks.append({
                    "解禁日期": str(r.get("解禁日期", "")),
                    "解禁数量": str(r.get("解禁数量", "")),
                    "解禁类型": str(r.get("限售类型", "")),
                })
            return {"code": code, "unlocks": unlocks}
        except Exception as e:
            logger.warning(f"get_restrict_stock_unlock 失败 [{code}]: {e}")
            return {"error": str(e)}
