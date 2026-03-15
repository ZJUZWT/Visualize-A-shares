"""投资专家 Agent 工具层 — 引擎调用适配"""

from typing import Any

import httpx
from loguru import logger

from expert.schemas import ToolCall


class ExpertTools:
    """专家 Agent 工具层 — 适配各引擎的调用"""

    def __init__(self, data_engine, cluster_engine, llm_engine=None, api_base: str = "http://localhost:8000"):
        self.data_engine = data_engine
        self.cluster_engine = cluster_engine
        self.llm_engine = llm_engine
        self.api_base = api_base
        self.http_client = httpx.Client(timeout=30.0)

    def execute_tool_call(self, tool_call: ToolCall) -> dict[str, Any]:
        """执行工具调用"""
        engine = tool_call.engine
        action = tool_call.action
        params = tool_call.params

        logger.debug(f"执行工具调用: {engine}.{action} with {params}")

        if engine == "data":
            return self._call_data_engine(action, params)
        elif engine == "cluster":
            return self._call_cluster_engine(action, params)
        elif engine == "llm":
            return self._call_llm_engine(action, params)
        else:
            return {"error": f"Unknown engine: {engine}"}

    def _call_data_engine(self, action: str, params: dict) -> dict[str, Any]:
        """调用数据引擎"""
        try:
            if action == "search_stock":
                query = params.get("query", "")
                limit = params.get("limit", 20)
                snapshot = self.data_engine.get_snapshot()
                if snapshot.empty:
                    return {"error": "No snapshot data"}
                q_lower = query.lower()
                results = []
                for _, row in snapshot.iterrows():
                    code = str(row.get("code", ""))
                    name = str(row.get("name", ""))
                    if q_lower in code.lower() or q_lower in name.lower():
                        results.append({
                            "code": code,
                            "name": name,
                            "price": float(row.get("price", 0)),
                            "pct_chg": float(row.get("pct_chg", 0)),
                        })
                    if len(results) >= limit:
                        break
                return {"results": results}

            elif action == "get_stock_info":
                code = params.get("code", "")
                snapshot = self.data_engine.get_snapshot()
                if snapshot.empty:
                    return {"error": "No snapshot data"}
                for _, row in snapshot.iterrows():
                    if str(row.get("code", "")) == code:
                        return {
                            "code": code,
                            "name": str(row.get("name", "")),
                            "price": float(row.get("price", 0)),
                            "pct_chg": float(row.get("pct_chg", 0)),
                            "volume": int(row.get("volume", 0)),
                            "amount": float(row.get("amount", 0)),
                            "pe_ttm": float(row.get("pe_ttm", 0)),
                            "pb": float(row.get("pb", 0)),
                        }
                return {"error": f"Stock not found: {code}"}

            elif action == "get_daily_history":
                code = params.get("code", "")
                days = params.get("days", 60)
                import datetime
                end = datetime.date.today().strftime("%Y-%m-%d")
                start = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
                df = self.data_engine.get_daily_history(code, start, end)
                if df.empty:
                    return {"error": f"No history for {code}"}
                return {
                    "code": code,
                    "history": df.to_dict("records")
                }

            else:
                return {"error": f"Unknown data action: {action}"}

        except Exception as e:
            logger.error(f"数据引擎调用失败: {e}")
            return {"error": str(e)}

    def _call_cluster_engine(self, action: str, params: dict) -> dict[str, Any]:
        """调用聚类引擎"""
        try:
            if action == "search_stocks":
                query = params.get("query", "")
                limit = params.get("limit", 20)
                results = self.cluster_engine.search_stocks(query, limit)
                return {"results": results}

            elif action == "get_cluster_for_stock":
                code = params.get("code", "")
                cluster_info = self.cluster_engine.get_cluster_for_stock(code)
                if cluster_info is None:
                    return {"error": f"Stock not found: {code}"}
                return cluster_info

            else:
                return {"error": f"Unknown cluster action: {action}"}

        except Exception as e:
            logger.error(f"聚类引擎调用失败: {e}")
            return {"error": str(e)}

    def _call_llm_engine(self, action: str, params: dict) -> dict[str, Any]:
        """调用 LLM 引擎"""
        try:
            if action == "chat":
                message = params.get("message", "")
                if not self.llm_engine:
                    return {"error": "LLM engine not available"}
                response = self.llm_engine.chat(message)
                return {"response": response}

            else:
                return {"error": f"Unknown llm action: {action}"}

        except Exception as e:
            logger.error(f"LLM 引擎调用失败: {e}")
            return {"error": str(e)}

    def run_debate(self, code: str, max_rounds: int = 3) -> str:
        """运行辩论并消费 SSE 流"""
        try:
            url = f"{self.api_base}/api/v1/debate/start"
            payload = {"code": code, "max_rounds": max_rounds}

            with self.http_client.stream("POST", url, json=payload) as response:
                if response.status_code != 200:
                    logger.error(f"辩论启动失败: {response.status_code}")
                    return ""

                debate_id = None
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        try:
                            import json
                            data = json.loads(line[6:])
                            if "debate_id" in data:
                                debate_id = data["debate_id"]
                            logger.debug(f"辩论流: {data}")
                        except Exception as e:
                            logger.debug(f"解析 SSE 行失败: {e}")

                return debate_id or ""

        except Exception as e:
            logger.error(f"辩论运行失败: {e}")
            return ""

    def close(self):
        """关闭 HTTP 客户端"""
        self.http_client.close()
