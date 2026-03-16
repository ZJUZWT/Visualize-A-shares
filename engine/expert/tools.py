"""投资专家 Agent 工具层 — 引擎调用适配"""

import asyncio
import json
from typing import Any

import httpx
from loguru import logger

from expert.schemas import ToolCall


class ExpertTools:
    """专家 Agent 工具层 — 适配各引擎的调用"""

    def __init__(
        self,
        data_engine=None,
        cluster_engine=None,
        llm_engine=None,
        api_base: str = "http://localhost:8000",
    ):
        self.data_engine = data_engine
        self.cluster_engine = cluster_engine
        self.llm_engine = llm_engine
        self.api_base = api_base

    async def execute(self, engine: str, action: str, params: dict) -> str:
        """异步执行工具调用，返回摘要字符串"""
        logger.debug(f"执行工具调用: {engine}.{action} with {params}")
        try:
            if engine == "data":
                result = self._call_data_engine(action, params)
            elif engine == "quant":
                result = await self._call_quant_engine(action, params)
            elif engine == "cluster":
                result = self._call_cluster_engine(action, params)
            elif engine == "expert":
                # 调用引擎专家（聚合者模式）
                return await self._ask_expert(action, params)
            elif engine == "debate":
                if action == "start":
                    return await self._run_debate(
                        code=params.get("code", ""),
                        max_rounds=params.get("max_rounds", 2),
                    )
                result = {"error": f"Unknown debate action: {action}"}
            else:
                result = {"error": f"Unknown engine: {engine}"}

            summary = json.dumps(result, ensure_ascii=False, default=str)
            return summary[:500]
        except Exception as e:
            logger.error(f"工具调用失败 {engine}.{action}: {e}")
            return f"工具调用失败: {e}"

    # ── 引擎专家聚合 ────────────────────────────────────

    async def _ask_expert(self, action: str, params: dict) -> str:
        """调用引擎专家，消费 SSE 流，返回完整回复文本

        action 就是 expert_type: data / quant / info / industry
        params: {"question": "..."}
        """
        expert_type = action
        question = params.get("question", "")
        if not question:
            return "缺少 question 参数"

        url = f"{self.api_base}/api/v1/expert/chat/{expert_type}"
        full_text = ""
        tool_summaries: list[str] = []

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)
            ) as client:
                async with client.stream(
                    "POST", url,
                    json={"message": question},
                    headers={"Content-Type": "application/json"},
                ) as response:
                    if response.status_code != 200:
                        return f"专家 {expert_type} 请求失败: HTTP {response.status_code}"

                    event_type = ""
                    async for line in response.aiter_lines():
                        if line.startswith("event:"):
                            event_type = line[6:].strip()
                        elif line.startswith("data:"):
                            data_str = line[5:].strip()
                            if not data_str:
                                continue
                            try:
                                data = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue

                            if event_type == "reply_token":
                                full_text += data.get("token", "")
                            elif event_type == "reply_complete":
                                full_text = data.get("full_text", full_text)
                            elif event_type == "tool_call":
                                tool_summaries.append(
                                    f"调用了 {data.get('engine','')}.{data.get('action','')}"
                                )
                            elif event_type == "tool_result":
                                tool_summaries.append(
                                    f"结果: {data.get('summary', '')[:100]}"
                                )
                            elif event_type == "error":
                                return f"专家 {expert_type} 错误: {data.get('message', '')}"

        except asyncio.TimeoutError:
            return f"专家 {expert_type} 响应超时(120s)，已获取部分: {full_text[:300]}"
        except Exception as e:
            logger.error(f"ask_expert({expert_type}) 失败: {e}")
            return f"调用专家 {expert_type} 失败: {e}"

        if not full_text:
            return f"专家 {expert_type} 未返回有效内容"

        # 组装结果：工具调用摘要 + 完整回复
        parts = []
        if tool_summaries:
            parts.append(f"[{expert_type}专家工具链] " + " → ".join(tool_summaries))
        parts.append(full_text)
        return "\n".join(parts)

    # ── 同步兼容旧接口 ──────────────────────────────────

    def execute_tool_call(self, tool_call: ToolCall) -> dict[str, Any]:
        """同步执行工具调用（旧接口兼容）"""
        engine = tool_call.engine
        action = tool_call.action
        params = tool_call.params
        logger.debug(f"执行工具调用(sync): {engine}.{action} with {params}")
        if engine == "data":
            return self._call_data_engine(action, params)
        elif engine == "cluster":
            return self._call_cluster_engine(action, params)
        else:
            return {"error": f"Unknown engine: {engine}"}

    # ── 数据引擎 ────────────────────────────────────────

    def _call_data_engine(self, action: str, params: dict) -> dict[str, Any]:
        """调用数据引擎"""
        if action == "get_current_date":
            import datetime
            now = datetime.datetime.now()
            return {
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
                "weekday": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()],
                "is_trading_day": now.weekday() < 5,
            }

        if self.data_engine is None:
            return {"error": "data_engine not available"}
        try:
            if action == "get_daily_history":
                import datetime
                code = params.get("code", "")
                days = params.get("days", 60)
                end = datetime.date.today().strftime("%Y-%m-%d")
                start = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
                df = self.data_engine.get_daily_history(code, start, end)
                if df.empty:
                    return {"error": f"No history for {code}"}
                records = df.tail(10).to_dict("records")
                return {"code": code, "history": records, "total_days": len(df)}

            elif action == "get_company_profile":
                code = params.get("code", "")
                profile = self.data_engine.get_company_profile(code)
                if profile is None:
                    return {"error": f"No profile for {code}"}
                return profile if isinstance(profile, dict) else {"profile": str(profile)}

            elif action == "search_stock":
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

            else:
                return {"error": f"Unknown data action: {action}"}

        except Exception as e:
            logger.error(f"数据引擎调用失败: {e}")
            return {"error": str(e)}

    # ── 量化引擎 ────────────────────────────────────────

    async def _call_quant_engine(self, action: str, params: dict) -> dict[str, Any]:
        """调用量化引擎（通过 HTTP）"""
        try:
            code = params.get("code", "")
            async with httpx.AsyncClient(timeout=30.0) as client:
                if action == "get_factor_scores":
                    resp = await client.get(f"{self.api_base}/api/v1/quant/factors/{code}")
                    resp.raise_for_status()
                    return resp.json()
                elif action == "get_technical_indicators":
                    resp = await client.get(f"{self.api_base}/api/v1/quant/indicators/{code}")
                    resp.raise_for_status()
                    return resp.json()
                else:
                    return {"error": f"Unknown quant action: {action}"}
        except Exception as e:
            logger.error(f"量化引擎调用失败: {e}")
            return {"error": str(e)}

    # ── 聚类引擎 ────────────────────────────────────────

    def _call_cluster_engine(self, action: str, params: dict) -> dict[str, Any]:
        """调用聚类引擎"""
        if self.cluster_engine is None:
            return {"error": "cluster_engine not available"}
        try:
            if action == "get_terrain_data":
                result = self.cluster_engine.get_terrain_data()
                return {"status": "ok", "clusters": len(result) if result else 0}
            elif action == "search_stocks":
                query = params.get("query", "")
                limit = params.get("limit", 20)
                results = self.cluster_engine.search_stocks(query, limit)
                return {"results": results}
            else:
                return {"error": f"Unknown cluster action: {action}"}
        except Exception as e:
            logger.error(f"聚类引擎调用失败: {e}")
            return {"error": str(e)}

    # ── 辩论工具 ────────────────────────────────────────

    async def _run_debate(self, code: str, max_rounds: int = 2) -> str:
        """触发专家辩论，消费完整 SSE 流，返回裁判裁决摘要（最长500字）"""
        url = f"{self.api_base}/api/v1/debate/start"
        payload = {"code": code, "max_rounds": max_rounds}
        judge_verdict = ""
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code != 200:
                        return f"辩论启动失败: HTTP {response.status_code}"
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if not data_str:
                            continue
                        try:
                            data = json.loads(data_str)
                            # 提取 judge_verdict summary
                            if isinstance(data, dict):
                                if data.get("event") == "judge_verdict" or "summary" in data:
                                    summary = data.get("summary") or data.get("data", {}).get("summary", "")
                                    if summary:
                                        judge_verdict = summary
                        except (json.JSONDecodeError, Exception):
                            continue
        except asyncio.TimeoutError:
            return f"辩论超时（180s），已获取部分结果: {judge_verdict[:200]}"
        except Exception as e:
            logger.error(f"辩论运行失败: {e}")
            return f"辩论运行失败: {e}"

        return judge_verdict[:500] if judge_verdict else "辩论完成，未获取到裁判裁决"
