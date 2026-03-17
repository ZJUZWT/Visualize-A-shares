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
    "get_sector_overview", "get_macro_context",
}

# 不需要 code 参数的 action（跳过 code 解析守卫）
NO_CODE_ACTIONS: set[str] = {"get_sector_overview", "get_macro_context"}

ACTION_DISPATCH: dict[str, tuple[str, str, str, bool]] = {
    # action → (module_name, getter_fn, method_name, is_async)
    "get_stock_info":           ("engine.data",     "get_data_engine",    "get_profile",           False),
    "get_news":                 ("engine.info",     "get_info_engine",    "get_news",              True),
    "get_announcements":        ("engine.info",     "get_info_engine",    "get_announcements",     True),
    "get_cluster_for_stock":    ("engine.cluster",  "get_cluster_engine", "get_cluster_for_stock", False),
    "get_industry_cognition":   ("engine.industry", "get_industry_engine", "analyze",             True),
    "get_capital_structure":    ("engine.industry", "get_industry_engine", "get_capital_structure", True),
}


class DataFetcher:
    """从各引擎收集 Agent 所需数据

    Phase 1 MVP: 直接调用引擎 Python 接口。
    Phase 2+: 通过 MCP Tool 调用。
    """

    def __init__(self, as_of_date: str = ""):
        # 辩论时间锚点，空字符串时 fallback 到 today
        self._as_of_date = as_of_date

    @property
    def end_date(self) -> str:
        """数据拉取的截止日期"""
        return self._as_of_date or datetime.date.today().strftime("%Y-%m-%d")

    def _start_date(self, days: int = 90) -> str:
        """从 end_date 往前推 N 天"""
        end = datetime.date.fromisoformat(self.end_date)
        return (end - datetime.timedelta(days=days)).strftime("%Y-%m-%d")

    def get_stock_data(self, target: str) -> dict:
        """获取基本面数据（DataEngine + ClusterEngine）"""
        try:
            from engine.data import get_data_engine
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
            from engine.quant import get_quant_engine
            from engine.data import get_data_engine

            de = get_data_engine()
            daily = de.get_daily_history(target, self._start_date(90), self.end_date)

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
            from engine.info import get_info_engine
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
        # NO_CODE_ACTIONS 跳过 code 解析守卫
        if req.action not in NO_CODE_ACTIONS:
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
            return result
        else:
            raise ValueError(f"不支持的 action: {req.action}")

    def _resolve_code(self, name: str) -> str:
        """按名称模糊匹配股票代码，找不到返回空字符串"""
        try:
            from engine.data import get_data_engine
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
        """获取最新一期财报关键指标（回测模式下只返回 as_of_date 之前的财报）"""
        try:
            import akshare as ak
            df = ak.stock_financial_analysis_indicator(symbol=code, start_year="2020")
            if df is None or df.empty:
                return {"error": f"无财务数据: {code}"}
            # 回测模式：过滤掉 as_of_date 之后的财报
            if self._as_of_date and "日期" in df.columns:
                df["日期"] = pd.to_datetime(df["日期"], errors="coerce")
                cutoff = pd.Timestamp(self._as_of_date)
                df = df[df["日期"] <= cutoff]
                if df.empty:
                    return {"error": f"无 {self._as_of_date} 之前的财务数据: {code}"}
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
        """获取资金流向（回测模式下返回 as_of_date 当日或之前最近一日的数据）"""
        try:
            import akshare as ak
            market = "sh" if code.startswith("6") else "sz"
            df = ak.stock_individual_fund_flow(stock=code, market=market)
            if df is None or df.empty:
                return {"error": f"无资金流向数据: {code}"}
            # 回测模式：过滤到 as_of_date 之前的数据
            if self._as_of_date and "日期" in df.columns:
                df["日期"] = pd.to_datetime(df["日期"], errors="coerce")
                cutoff = pd.Timestamp(self._as_of_date)
                df = df[df["日期"] <= cutoff]
                if df.empty:
                    return {"error": f"无 {self._as_of_date} 之前的资金流向数据: {code}"}
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
            from engine.data import get_data_engine
            de = get_data_engine()
            df = de.get_daily_history(code, self._start_date(days), self.end_date)
            if not isinstance(df, pd.DataFrame) or df.empty:
                return {"error": f"无日线数据: {code}"}
            rows = df.tail(20).to_dict(orient="records")
            return {"code": code, "days": len(df), "recent": rows, "as_of_date": self.end_date}
        except Exception as e:
            logger.warning(f"get_daily_history 失败 [{code}]: {e}")
            return {"error": str(e)}

    def get_technical_indicators(self, code: str, days: int = 60) -> dict:
        """获取技术指标（RSI/MACD/布林带）"""
        try:
            from engine.data import get_data_engine
            from engine.quant import get_quant_engine
            de = get_data_engine()
            df = de.get_daily_history(code, self._start_date(days), self.end_date)
            if not isinstance(df, pd.DataFrame) or df.empty:
                return {"error": f"无日线数据: {code}"}
            qe = get_quant_engine()
            indicators = qe.compute_indicators(df)
            return {"code": code, **indicators}
        except Exception as e:
            logger.warning(f"get_technical_indicators 失败 [{code}]: {e}")
            return {"error": str(e)}

    def get_factor_scores(self, code: str) -> dict:
        """获取个股因子评分（技术指标 + 因子权重）"""
        try:
            from engine.data import get_data_engine
            from engine.quant import get_quant_engine
            de = get_data_engine()
            df = de.get_daily_history(code, self._start_date(90), self.end_date)
            if not isinstance(df, pd.DataFrame) or df.empty:
                return {"error": f"无日线数据: {code}"}
            qe = get_quant_engine()
            indicators = qe.compute_indicators(df)
            weights, weight_source = qe.get_factor_weights()
            factor_defs = [
                {"name": f.name, "direction": f.direction, "weight": weights.get(f.name, f.default_weight)}
                for f in qe.get_factor_defs()
            ]
            return {
                "code": code,
                "indicators": indicators,
                "factor_defs": factor_defs,
                "weight_source": weight_source,
            }
        except Exception as e:
            logger.warning(f"get_factor_scores 失败 [{code}]: {e}")
            return {"error": str(e)}

    def get_northbound_holding(self, code: str) -> dict:
        """获取北向持股数据（回测模式下返回 as_of_date 当日或之前最近一日的数据）"""
        try:
            import akshare as ak
            df = ak.stock_hsgt_individual_em(symbol=code)
            if df is None or df.empty:
                return {"error": f"无北向持股数据: {code}"}
            # 回测模式：过滤到 as_of_date 之前的数据
            if self._as_of_date and "日期" in df.columns:
                df["日期"] = pd.to_datetime(df["日期"], errors="coerce")
                cutoff = pd.Timestamp(self._as_of_date)
                df = df[df["日期"] <= cutoff]
                if df.empty:
                    return {"error": f"无 {self._as_of_date} 之前的北向持股数据: {code}"}
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
        """获取融资融券余额 — 仅上交所(6开头)可用，深交所 AKShare 接口暂不可用"""
        try:
            import akshare as ak
            if not code.startswith("6"):
                return {"error": f"融资融券明细仅支持上交所(6开头)股票，{code} 为深交所标的，AKShare 深交所接口暂不可用"}
            # 从 as_of_date 往前尝试最近 5 个交易日
            end = datetime.date.fromisoformat(self.end_date)
            df = None
            date_str = ""
            for offset in range(5):
                d = (end - datetime.timedelta(days=offset)).strftime("%Y%m%d")
                try:
                    df = ak.stock_margin_detail_sse(date=d)
                    if df is not None and not df.empty:
                        date_str = d
                        break
                except Exception:
                    continue
            if df is None or df.empty:
                return {"error": f"无融资融券数据: {code}（最近5日均无数据）"}
            # 按 标的证券代码 过滤
            match = df[df["标的证券代码"].astype(str) == code]
            if match.empty:
                return {"error": f"融资融券数据中未找到 {code}"}
            row = match.iloc[0]
            return {
                "code": code, "date": date_str,
                "融资余额": str(row.get("融资余额", "")),
                "融资买入额": str(row.get("融资买入额", "")),
                "融券余量": str(row.get("融券余量", "")),
            }
        except Exception as e:
            logger.warning(f"get_margin_balance 失败 [{code}]: {e}")
            return {"error": str(e)}

    def get_turnover_rate(self, code: str) -> dict:
        """获取换手率（回测模式下从日线数据获取，实时模式从 snapshot 获取）"""
        try:
            # 回测模式：snapshot 只有最新数据，降级从日线历史获取
            if self._as_of_date:
                from engine.data import get_data_engine
                de = get_data_engine()
                df = de.get_daily_history(code, self._start_date(5), self.end_date)
                if isinstance(df, pd.DataFrame) and not df.empty and "turnover_rate" in df.columns:
                    return {"code": code, "turnover_rate": float(df.iloc[-1]["turnover_rate"]), "as_of_date": self.end_date}
                return {"error": f"无 {self._as_of_date} 的换手率数据: {code}"}
            from engine.data import get_data_engine
            snapshot = get_data_engine().get_snapshot()
            row = snapshot[snapshot["code"] == code]
            if row.empty:
                return {"error": f"未找到 {code}"}
            return {"code": code, "turnover_rate": float(row.iloc[0]["turnover_rate"])}
        except Exception as e:
            logger.warning(f"get_turnover_rate 失败 [{code}]: {e}")
            return {"error": str(e)}

    def get_restrict_stock_unlock(self, code: str) -> dict:
        """获取限售股解禁计划（未来 6 个月内）"""
        try:
            import akshare as ak
            end = datetime.date.fromisoformat(self.end_date)
            start_str = end.strftime("%Y%m%d")
            end_str = (end + datetime.timedelta(days=180)).strftime("%Y%m%d")
            df = ak.stock_restricted_release_detail_em(start_date=start_str, end_date=end_str)
            if df is None or df.empty:
                return {"code": code, "unlocks": []}
            # 按股票代码过滤
            match = df[df["股票代码"].astype(str) == code]
            if match.empty:
                return {"code": code, "unlocks": []}
            unlocks = []
            for _, r in match.head(5).iterrows():
                unlocks.append({
                    "解禁时间": str(r.get("解禁时间", "")),
                    "解禁数量": str(r.get("解禁数量", "")),
                    "实际解禁市值": str(r.get("实际解禁市值", "")),
                    "限售股类型": str(r.get("限售股类型", "")),
                    "占流通市值比例": str(r.get("占解禁前流通市值比例", "")),
                })
            return {"code": code, "unlocks": unlocks}
        except Exception as e:
            logger.warning(f"get_restrict_stock_unlock 失败 [{code}]: {e}")
            return {"error": str(e)}

    def get_sector_overview(self, sector: str) -> dict:
        """板块概览：成分股 Top 5 + 平均涨跌幅"""
        try:
            from engine.industry import get_industry_engine
            from engine.data import get_data_engine
            ie = get_industry_engine()
            de = get_data_engine()
            codes = ie.get_industry_stocks(sector)
            if not codes:
                return {"sector": sector, "top_stocks": [], "avg_pct_chg": 0.0}
            snapshot = de.get_snapshot()
            if snapshot is None or snapshot.empty or "code" not in snapshot.columns:
                return {"sector": sector, "top_stocks": [], "avg_pct_chg": 0.0}
            sector_df = snapshot[snapshot["code"].isin(codes)]
            if sector_df.empty:
                return {"sector": sector, "top_stocks": [], "avg_pct_chg": 0.0}
            avg_pct = float(sector_df["pct_chg"].mean()) if "pct_chg" in sector_df.columns else 0.0
            # Top 5 by total_mv
            sort_col = "total_mv" if "total_mv" in sector_df.columns else "pct_chg"
            top5 = sector_df.nlargest(5, sort_col)
            profiles = de.get_profiles()
            top_stocks = []
            for _, row in top5.iterrows():
                c = row["code"]
                name = profiles.get(c, {}).get("name", c)
                top_stocks.append({
                    "code": c,
                    "name": name,
                    "pct_chg": row.get("pct_chg", 0.0),
                    "pe_ttm": row.get("pe_ttm", None),
                    "total_mv": row.get("total_mv", None),
                })
            return {"sector": sector, "top_stocks": top_stocks, "avg_pct_chg": round(avg_pct, 4)}
        except Exception as e:
            logger.warning(f"get_sector_overview 失败 [{sector}]: {e}")
            return {"sector": sector, "top_stocks": [], "avg_pct_chg": 0.0}

    def get_macro_context(self, query: str) -> dict:
        """宏观上下文（best-effort）：涨跌比 + 行业热力图"""
        try:
            from engine.data import get_data_engine
            snapshot = get_data_engine().get_snapshot()
            result: dict = {"advance_decline_ratio": None, "sector_heatmap": None,
                            "note": "宏观数据为 best-effort，不含北向资金等市场级别接口"}
            if snapshot is None or snapshot.empty or "pct_chg" not in snapshot.columns:
                return result
            # 涨跌比
            total = len(snapshot)
            up = int((snapshot["pct_chg"] > 0).sum())
            result["advance_decline_ratio"] = round(up / max(total, 1), 4)
            # 行业板块涨跌幅排行
            if "industry" in snapshot.columns:
                grouped = snapshot[snapshot["industry"].notna() & (snapshot["industry"] != "")]
                if not grouped.empty:
                    heatmap = (
                        grouped.groupby("industry")["pct_chg"]
                        .mean()
                        .sort_values(ascending=False)
                        .head(20)
                    )
                    result["sector_heatmap"] = [
                        {"industry": ind, "avg_pct_chg": round(val, 4)}
                        for ind, val in heatmap.items()
                    ]
            return result
        except Exception as e:
            logger.warning(f"get_macro_context 失败: {e}")
            return {"advance_decline_ratio": None, "sector_heatmap": None,
                    "note": "宏观数据暂不可用"}
