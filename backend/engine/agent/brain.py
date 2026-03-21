"""
AgentBrain — Main Agent 决策大脑

每次运行流程：
1. 标的筛选（watchlist + 量化筛选 + 已有持仓）
2. 逐标的分析（调用专家工具层获取数据）
3. LLM 综合决策
4. 自动执行（生成 trade_plan → execute_trade）
"""
from __future__ import annotations

import json
import time
import traceback
import uuid
from datetime import date, datetime

from loguru import logger

from engine.agent.db import AgentDB
from engine.agent.models import TradePlanInput, TradeInput
from engine.agent.service import AgentService
from engine.agent.validator import TradeValidator


class AgentBrain:
    """Agent 决策大脑"""

    def __init__(self, portfolio_id: str):
        self.portfolio_id = portfolio_id
        self.db = AgentDB.get_instance()
        self.service = AgentService(db=self.db, validator=TradeValidator())

    async def execute(self, run_id: str):
        """执行一次完整的分析→决策→执行流程"""
        start = time.monotonic()
        logger.info(f"🧠 AgentBrain 运行开始: run_id={run_id}")

        try:
            state_before = await self.service.get_agent_state(self.portfolio_id)
            await self.service.update_brain_run(run_id, {
                "state_before": state_before,
            })
            config = await self.service.get_brain_config()

            # Step 1: 标的筛选
            candidates = await self._select_candidates(config)
            await self.service.update_brain_run(run_id, {
                "candidates": candidates,
            })
            logger.info(f"🧠 候选标的: {len(candidates)} 只")

            if not candidates:
                elapsed = time.monotonic() - start
                state_after = await self.service.get_agent_state(self.portfolio_id)
                await self.service.update_brain_run(run_id, {
                    "status": "completed",
                    "decisions": [],
                    "state_after": state_after,
                    "execution_summary": {
                        "candidate_count": 0,
                        "analysis_count": 0,
                        "decision_count": 0,
                        "plan_count": 0,
                        "trade_count": 0,
                        "elapsed_seconds": round(elapsed, 4),
                    },
                })
                return

            # Step 2: 逐标的分析
            analysis_results = await self._analyze_candidates(candidates, config)
            await self.service.update_brain_run(run_id, {
                "analysis_results": analysis_results,
            })
            logger.info(f"🧠 分析完成: {len(analysis_results)} 只")

            # Step 3: LLM 综合决策
            portfolio = await self.service.get_portfolio(self.portfolio_id)
            decisions = await self._make_decisions(analysis_results, portfolio, config, run_id)
            await self.service.update_brain_run(run_id, {
                "decisions": decisions,
            })
            logger.info(f"🧠 决策完成: {len(decisions)} 个操作")

            # Step 4: 自动执行
            plan_ids, trade_ids = await self._execute_decisions(decisions)
            elapsed = time.monotonic() - start
            state_after = await self.service.get_agent_state(self.portfolio_id)
            await self.service.update_brain_run(run_id, {
                "status": "completed",
                "plan_ids": plan_ids,
                "trade_ids": trade_ids,
                "state_after": state_after,
                "execution_summary": {
                    "candidate_count": len(candidates),
                    "analysis_count": len(analysis_results),
                    "decision_count": len(decisions),
                    "plan_count": len(plan_ids),
                    "trade_count": len(trade_ids),
                    "elapsed_seconds": round(elapsed, 4),
                },
            })
            logger.info(f"🧠 AgentBrain 运行完成: {elapsed:.1f}s, {len(plan_ids)} plans, {len(trade_ids)} trades")

        except Exception as e:
            logger.error(f"🧠 AgentBrain 运行失败: {e}\n{traceback.format_exc()}")
            await self.service.update_brain_run(run_id, {
                "status": "failed",
                "error_message": str(e),
            })

    # ── Step 1: 标的筛选 ──────────────────────────────

    async def _select_candidates(self, config: dict) -> list[dict]:
        """合并 watchlist + 量化筛选 + 已有持仓"""
        watchlist = await self.service.list_watchlist()
        quant_top = await self._quant_screen(config.get("quant_top_n", 20))
        positions = await self.service.get_positions(self.portfolio_id, "open")

        return self._merge_candidates(
            watchlist, quant_top, positions,
            max_n=config.get("max_candidates", 30),
        )

    def _merge_candidates(
        self,
        watchlist: list[dict],
        quant_top: list[dict],
        positions: list[dict],
        max_n: int = 30,
    ) -> list[dict]:
        """合并去重候选标的"""
        seen = set()
        result = []

        # 已有持仓优先
        for p in positions:
            code = p["stock_code"]
            if code not in seen:
                seen.add(code)
                result.append({
                    "stock_code": code,
                    "stock_name": p.get("stock_name", code),
                    "source": "position",
                })

        # 关注列表
        for w in watchlist:
            code = w["stock_code"]
            if code not in seen:
                seen.add(code)
                result.append({
                    "stock_code": code,
                    "stock_name": w.get("stock_name", code),
                    "source": "watchlist",
                })

        # 量化筛选
        for q in quant_top:
            code = q["stock_code"]
            if code not in seen:
                seen.add(code)
                result.append({
                    "stock_code": code,
                    "stock_name": q.get("stock_name", code),
                    "source": "quant",
                    "score": q.get("score"),
                })

        return result[:max_n]

    async def _quant_screen(self, top_n: int = 20) -> list[dict]:
        """量化筛选 — 调用 QuantEngine 因子打分"""
        try:
            from engine.quant import get_quant_engine
            from engine.data import get_data_engine

            de = get_data_engine()
            snapshot_df = de.get_snapshot()
            if snapshot_df is None or snapshot_df.empty:
                logger.warning("🧠 量化筛选: snapshot 为空")
                return []

            qe = get_quant_engine()
            result = qe.predict(snapshot_df)

            sorted_preds = sorted(
                result.predictions.items(),
                key=lambda x: x[1],
                reverse=True,
            )[:top_n]

            return [
                {"stock_code": code, "score": round(score, 4), "stock_name": code}
                for code, score in sorted_preds
            ]
        except Exception as e:
            logger.warning(f"🧠 量化筛选失败: {e}")
            return []

    # ── Step 2: 逐标的分析 ────────────────────────────

    async def _analyze_candidates(self, candidates: list[dict], config: dict) -> list[dict]:
        """对每个候选标的调用专家工具层获取数据"""
        results = []
        for c in candidates:
            code = c["stock_code"]
            try:
                analysis = await self._analyze_single(code)
                analysis["stock_code"] = code
                analysis["stock_name"] = c.get("stock_name", code)
                analysis["source"] = c.get("source", "unknown")
                results.append(analysis)
            except Exception as e:
                logger.warning(f"🧠 分析 {code} 失败: {e}")
                results.append({
                    "stock_code": code,
                    "stock_name": c.get("stock_name", code),
                    "source": c.get("source", "unknown"),
                    "error": str(e),
                })
        return results

    async def _analyze_single(self, code: str) -> dict:
        """分析单个标的"""
        from engine.expert.tools import ExpertTools
        from engine.data import get_data_engine
        from engine.cluster import get_cluster_engine
        from llm import LLMProviderFactory, llm_settings

        de = get_data_engine()
        ce = get_cluster_engine()
        llm = LLMProviderFactory.create(llm_settings)
        tools = ExpertTools(de, ce, llm)

        analysis = {}

        try:
            analysis["daily"] = await tools.execute("data", "get_daily_history", {"code": code, "days": 30})
        except Exception as e:
            analysis["daily"] = f"获取失败: {e}"

        try:
            analysis["indicators"] = await tools.execute("quant", "get_technical_indicators", {"code": code})
        except Exception as e:
            analysis["indicators"] = f"获取失败: {e}"

        return analysis

    # ── Step 3: LLM 综合决策 ──────────────────────────

    async def _make_decisions(
        self, analysis_results: list[dict], portfolio: dict, config: dict, run_id: str
    ) -> list[dict]:
        """LLM 综合决策"""
        from llm import LLMProviderFactory, llm_settings
        from llm.providers import ChatMessage

        llm = LLMProviderFactory.create(llm_settings)

        positions_desc = ""
        for p in portfolio.get("positions", []):
            positions_desc += (
                f"  - {p['stock_code']} {p['stock_name']}: "
                f"{p['current_qty']}股, 成本{p['entry_price']}, 类型{p['holding_type']}\n"
            )
        if not positions_desc:
            positions_desc = "  （空仓）\n"

        analysis_desc = ""
        for a in analysis_results:
            analysis_desc += f"\n### {a['stock_code']} {a.get('stock_name', '')}\n"
            analysis_desc += f"来源: {a.get('source', 'unknown')}\n"
            if "daily" in a:
                daily_str = a["daily"] if isinstance(a["daily"], str) else str(a["daily"])
                analysis_desc += f"行情: {daily_str}\n"
            if "indicators" in a:
                ind_str = a["indicators"] if isinstance(a["indicators"], str) else str(a["indicators"])
                analysis_desc += f"技术指标: {ind_str}\n"
            if "error" in a:
                analysis_desc += f"分析失败: {a['error']}\n"

        single_pct = config.get("single_position_pct", 0.15)
        max_pos = config.get("max_position_count", 10)

        prompt = f"""你是一个专业的 A 股投资 Agent，基于以下分析数据做出交易决策。

## 当前账户状态
- 现金余额：{portfolio['cash_balance']:.2f}
- 总资产：{portfolio['total_asset']:.2f}
- 当前持仓：
{positions_desc}

## 候选标的分析
{analysis_desc}

## 决策规则
1. 单只股票仓位不超过总资产的 {single_pct * 100:.0f}%
2. 同时持仓不超过 {max_pos} 只
3. quantity 必须是 100 的整数倍
4. 必须设置止盈和止损价格
5. 对已有持仓：检查是否需要止盈/止损/加仓/减仓
6. 今天日期: {date.today().isoformat()}

请输出 JSON 数组，只包含需要操作的标的（不要输出 hold/ignore）：
```json
[
  {{
    "stock_code": "600519",
    "stock_name": "贵州茅台",
    "action": "buy",
    "price": 1750.0,
    "quantity": 100,
    "holding_type": "mid_term",
    "reasoning": "...",
    "take_profit": 2100.0,
    "stop_loss": 1650.0,
    "risk_note": "...",
    "invalidation": "...",
    "confidence": 0.8
  }}
]
```

如果没有值得操作的标的，输出空数组 `[]`。
只输出 JSON，不要其他文字。"""

        messages = [ChatMessage(role="user", content=prompt)]

        # 流式收集
        chunks: list[str] = []
        async for token in llm.chat_stream(messages):
            chunks.append(token)
        raw = "".join(chunks)

        # 解析 JSON
        try:
            json_str = raw
            if "```json" in raw:
                json_str = raw.split("```json")[1].split("```")[0]
            elif "```" in raw:
                json_str = raw.split("```")[1].split("```")[0]
            decisions = json.loads(json_str.strip())
            if not isinstance(decisions, list):
                decisions = []
        except (json.JSONDecodeError, IndexError):
            logger.warning(f"🧠 LLM 决策解析失败: {raw[:200]}")
            decisions = []

        await self.service.update_brain_run(run_id, {
            "thinking_process": {
                "prompt": prompt,
                "raw_output": raw,
                "parsed_decisions": decisions,
            },
        })

        return decisions

    # ── Step 4: 自动执行 ──────────────────────────────

    async def _execute_decisions(self, decisions: list[dict]) -> tuple[list[str], list[str]]:
        """执行决策：生成 trade_plan → execute_trade"""
        plan_ids: list[str] = []
        trade_ids: list[str] = []
        trade_date = date.today().isoformat()

        for d in decisions:
            action = d.get("action", "")
            if action in ("hold", "ignore", ""):
                continue

            try:
                # 1. 生成 trade_plan
                direction = "buy" if action in ("buy", "add") else "sell"
                plan = await self.service.create_plan(TradePlanInput(
                    stock_code=d["stock_code"],
                    stock_name=d.get("stock_name", d["stock_code"]),
                    direction=direction,
                    entry_price=d.get("price"),
                    position_pct=d.get("position_pct"),
                    take_profit=d.get("take_profit"),
                    stop_loss=d.get("stop_loss"),
                    stop_loss_method=d.get("stop_loss_method"),
                    take_profit_method=d.get("take_profit_method"),
                    reasoning=d.get("reasoning", "Agent 自动决策"),
                    risk_note=d.get("risk_note"),
                    invalidation=d.get("invalidation"),
                    source_type="agent",
                ))
                plan_ids.append(plan["id"])

                # 2. 执行交易
                position_id = None
                holding_type = d.get("holding_type", "mid_term")

                if action in ("sell", "reduce"):
                    positions = await self.service.get_positions(self.portfolio_id, "open")
                    for p in positions:
                        if p["stock_code"] == d["stock_code"]:
                            position_id = p["id"]
                            holding_type = p.get("holding_type", holding_type)
                            break
                    if not position_id:
                        logger.warning(f"🧠 卖出 {d['stock_code']} 但未找到持仓，跳过")
                        continue

                if action == "add":
                    positions = await self.service.get_positions(self.portfolio_id, "open")
                    for p in positions:
                        if p["stock_code"] == d["stock_code"]:
                            position_id = p["id"]
                            break

                trade_input = TradeInput(
                    action=action,
                    stock_code=d["stock_code"],
                    price=d.get("price", 0),
                    quantity=d.get("quantity", 100),
                    holding_type=holding_type if action == "buy" else None,
                    reason=d.get("reasoning", "Agent 自动决策"),
                    thesis=d.get("reasoning", ""),
                    data_basis=["agent_brain_analysis"],
                    risk_note=d.get("risk_note", ""),
                    invalidation=d.get("invalidation", ""),
                    triggered_by="agent",
                )

                result = await self.service.execute_trade(
                    self.portfolio_id, trade_input, trade_date,
                    position_id=position_id,
                    stock_name=d.get("stock_name"),
                )
                if result.get("trade"):
                    trade_ids.append(result["trade"]["id"])

                # 3. 更新 plan 状态
                await self.service.update_plan(plan["id"], {"status": "executing"})

                logger.info(f"🧠 执行: {action} {d['stock_code']} x{d.get('quantity', 100)}")

            except Exception as e:
                logger.warning(f"🧠 执行 {d['stock_code']} 失败: {e}")

        return plan_ids, trade_ids
