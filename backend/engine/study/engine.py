"""StudyEngine — 离线自学习引擎

按需触发让 agent 自主学习：拉数据、多角度分析、沉淀知识到三层记忆。
学习结果写入 Knowledge Graph + Agent Memory + RAG Store，与用户对话无关。
"""

import asyncio
import json
import re
import time
import uuid
from datetime import datetime
from typing import Any

import duckdb
from loguru import logger
from pathlib import Path

from config import settings
from llm.config import llm_settings
from llm.providers import LLMProviderFactory, ChatMessage, BaseLLMProvider


# ─── DuckDB 表初始化 ──────────────────────────────────
_INIT_SQL = """
CREATE SCHEMA IF NOT EXISTS study;

CREATE TABLE IF NOT EXISTS study.tasks (
    id VARCHAR PRIMARY KEY,
    target VARCHAR NOT NULL,
    target_type VARCHAR NOT NULL,
    depth VARCHAR NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'pending',
    progress DOUBLE DEFAULT 0.0,
    current_step VARCHAR DEFAULT '',
    sub_tasks JSON DEFAULT '[]',
    result_summary TEXT DEFAULT '',
    beliefs_added INTEGER DEFAULT 0,
    error_message TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT now(),
    completed_at TIMESTAMP
);
"""


def _get_db_path() -> Path:
    return Path(settings.datasource.duckdb_path)


def _ensure_tables(conn: duckdb.DuckDBPyConnection) -> None:
    """确保 study schema + tasks 表存在"""
    for stmt in _INIT_SQL.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt)


# ─── LLM Prompt 模板 ──────────────────────────────────

QUICK_ANALYZE_PROMPT = """你是一位资深投研分析师。请基于以下数据，对 {stock_name}({code}) 进行全方位研判。

## 基本面数据
{fundamental}

## 量化/技术数据
{quant}

## 新闻资讯
{info}

## 产业链认知
{industry}

请输出严格的 JSON（不要包含 markdown 代码块标记）：
{{
  "beliefs": [
    {{"content": "一句话描述认知", "confidence": 0.0到1.0的浮点数, "category": "基本面|技术面|资讯面|产业链"}}
  ],
  "entities": [
    {{"type": "stock|sector|event", "name": "实体名称", "relations": ["与{stock_name}的关系描述"]}}
  ],
  "key_findings": "200字以内的核心发现",
  "risk_alerts": ["风险提示1", "风险提示2"],
  "stance": "bullish|bearish|neutral",
  "stance_confidence": 0.0到1.0的浮点数,
  "data_summary": "数据专家摘要",
  "quant_summary": "量化专家摘要",
  "info_summary": "资讯专家摘要",
  "industry_summary": "产业链专家摘要"
}}"""

DEEP_FUNDAMENTAL_PROMPT = """你是一位基本面分析专家。请基于以下数据，分析 {stock_name}({code}) 的基本面状况。

## 行情数据
{fundamental}

## 因子评分
{quant}

请输出严格的 JSON（不要包含 markdown 代码块标记）：
{{
  "beliefs": [{{"content": "...", "confidence": 0.0-1.0, "category": "基本面"}}],
  "summary": "基本面分析摘要（200字以内）",
  "risk_alerts": ["..."]
}}"""

DEEP_TECHNICAL_PROMPT = """你是一位技术分析专家。请基于以下技术数据，分析 {stock_name}({code}) 的技术面状况。

## 量化/技术指标
{quant}

## 近期行情
{fundamental}

请输出严格的 JSON（不要包含 markdown 代码块标记）：
{{
  "beliefs": [{{"content": "...", "confidence": 0.0-1.0, "category": "技术面"}}],
  "summary": "技术面分析摘要（200字以内）",
  "risk_alerts": ["..."]
}}"""

DEEP_INFO_PROMPT = """你是一位资讯分析专家。请基于以下新闻和公告数据，分析 {stock_name}({code}) 的资讯面状况。

## 新闻资讯
{info}

请输出严格的 JSON（不要包含 markdown 代码块标记）：
{{
  "beliefs": [{{"content": "...", "confidence": 0.0-1.0, "category": "资讯面"}}],
  "summary": "资讯面分析摘要（200字以内）",
  "risk_alerts": ["..."]
}}"""

DEEP_SYNTHESIS_PROMPT = """你是一位综合投研分析师。请基于以下多维度分析结果，对 {stock_name}({code}) 做最终综合研判。

## 基本面分析
{fundamental_analysis}

## 技术面分析
{technical_analysis}

## 资讯面分析
{info_analysis}

## 产业链认知
{industry}

请输出严格的 JSON（不要包含 markdown 代码块标记）：
{{
  "beliefs": [{{"content": "...", "confidence": 0.0-1.0, "category": "基本面|技术面|资讯面|产业链"}}],
  "entities": [{{"type": "stock|sector|event", "name": "...", "relations": ["..."]}}],
  "key_findings": "200字以内的核心发现",
  "risk_alerts": ["..."],
  "stance": "bullish|bearish|neutral",
  "stance_confidence": 0.0到1.0的浮点数,
  "data_summary": "数据专家摘要",
  "quant_summary": "量化专家摘要",
  "info_summary": "资讯专家摘要",
  "industry_summary": "产业链专家摘要"
}}"""


def _parse_json_from_llm(text: str) -> dict:
    """从 LLM 输出中提取 JSON，兼容 markdown 代码块"""
    # 尝试去掉 markdown 代码块
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", text.strip())
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # 尝试找第一个 { 和最后一个 }
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError:
                pass
        logger.warning(f"无法解析 LLM JSON 输出: {cleaned[:200]}")
        return {}


class StudyEngine:
    """离线自学习引擎

    核心流程:
    1. 解析目标（个股 / 行业）
    2. 数据采集（DataFetcher + 各引擎）
    3. LLM 分析（quick 单次 / deep 多轮）
    4. 写入三层记忆（Knowledge Graph + Agent Memory + RAG Store）
    5. DuckDB 记录进度
    """

    def __init__(self):
        self._conn = duckdb.connect(str(_get_db_path()))
        _ensure_tables(self._conn)
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._llm: BaseLLMProvider | None = None
        logger.info("StudyEngine 已初始化")

    def _get_llm(self) -> BaseLLMProvider | None:
        """延迟初始化 LLM Provider"""
        if self._llm is None and llm_settings.api_key:
            self._llm = LLMProviderFactory.create(llm_settings)
        return self._llm

    # ─── 公开 API ──────────────────────────────────────

    async def create_task(self, target: str, depth: str = "quick") -> dict:
        """创建学习任务

        target: 股票代码/名称/行业名
        depth: "quick" 单次分析 | "deep" 多轮分析
        """
        task_id = str(uuid.uuid4())[:8]
        target_type = self._resolve_target_type(target)
        resolved_target = target

        # 如果是股票名称，尝试解析为代码
        if target_type == "stock" and not re.fullmatch(r"\d{6}", target):
            code = self._resolve_stock_code(target)
            if code:
                resolved_target = code
            else:
                target_type = "industry"  # 解析失败，当行业处理

        sub_tasks: list[dict] = []
        if target_type == "industry":
            # 获取行业成分股，拆分子任务
            stocks = self._get_industry_stocks(resolved_target)
            # 取市值前 10 或全部（如果不到10个）
            for s in stocks[:10]:
                sub_tasks.append({
                    "code": s["code"],
                    "name": s.get("name", s["code"]),
                    "status": "pending",
                })

        self._conn.execute(
            """INSERT INTO study.tasks
               (id, target, target_type, depth, status, sub_tasks, created_at)
               VALUES (?, ?, ?, ?, 'pending', ?, now())""",
            [task_id, resolved_target, target_type, depth, json.dumps(sub_tasks)],
        )

        # 启动后台任务
        asyncio_task = asyncio.create_task(self._run_task(task_id, resolved_target, target_type, depth, sub_tasks))
        self._running_tasks[task_id] = asyncio_task

        task = self.get_task(task_id)
        logger.info(f"📚 学习任务创建: {task_id} target={resolved_target} type={target_type} depth={depth}")
        return task

    def list_tasks(self, status_filter: str = "") -> list[dict]:
        """查询任务列表"""
        if status_filter:
            rows = self._conn.execute(
                "SELECT * FROM study.tasks WHERE status = ? ORDER BY created_at DESC",
                [status_filter],
            ).fetchdf()
        else:
            rows = self._conn.execute(
                "SELECT * FROM study.tasks ORDER BY created_at DESC"
            ).fetchdf()

        if rows.empty:
            return []
        return rows.to_dict(orient="records")

    def get_task(self, task_id: str) -> dict:
        """查询单个任务"""
        rows = self._conn.execute(
            "SELECT * FROM study.tasks WHERE id = ?", [task_id]
        ).fetchdf()
        if rows.empty:
            return {"error": f"任务不存在: {task_id}"}
        record = rows.iloc[0].to_dict()
        # 解析 sub_tasks JSON
        if isinstance(record.get("sub_tasks"), str):
            try:
                record["sub_tasks"] = json.loads(record["sub_tasks"])
            except (json.JSONDecodeError, TypeError):
                record["sub_tasks"] = []
        return record

    async def cancel_task(self, task_id: str) -> dict:
        """取消任务"""
        task = self.get_task(task_id)
        if "error" in task:
            return task
        if task["status"] in ("completed", "cancelled", "failed"):
            return {"message": f"任务已处于终态: {task['status']}"}

        # 取消 asyncio task
        if task_id in self._running_tasks:
            self._running_tasks[task_id].cancel()
            del self._running_tasks[task_id]

        self._conn.execute(
            "UPDATE study.tasks SET status = 'cancelled' WHERE id = ?", [task_id]
        )
        logger.info(f"📚 学习任务已取消: {task_id}")
        return {"message": "已取消", "task_id": task_id}

    # ─── 内部实现 ──────────────────────────────────────

    def _resolve_target_type(self, target: str) -> str:
        """判断目标是个股还是行业"""
        if re.fullmatch(r"\d{6}", target):
            return "stock"
        # 尝试用 industry_engine 判断
        try:
            from engine.industry import get_industry_engine
            ie = get_industry_engine()
            stocks = ie.get_industry_stocks(target)
            if stocks:
                return "industry"
        except Exception:
            pass
        # 尝试解析为股票名称
        code = self._resolve_stock_code(target)
        if code:
            return "stock"
        return "industry"  # 默认当行业

    def _resolve_stock_code(self, name: str) -> str:
        """模糊匹配股票名称 → 代码"""
        try:
            from engine.data import get_data_engine
            profiles = get_data_engine().get_profiles()
            name_lower = name.lower()
            for code, info in profiles.items():
                stock_name = info.get("name", "")
                if stock_name and (stock_name == name or name_lower in stock_name.lower()):
                    return code
        except Exception as e:
            logger.warning(f"解析股票名称失败: {e}")
        return ""

    def _get_industry_stocks(self, industry: str) -> list[dict]:
        """获取行业成分股列表（按市值排序）"""
        try:
            from engine.industry import get_industry_engine
            from engine.data import get_data_engine
            ie = get_industry_engine()
            de = get_data_engine()
            codes = ie.get_industry_stocks(industry)
            if not codes:
                return []
            profiles = de.get_profiles()
            snapshot = de.get_snapshot()
            stocks = []
            for code in codes:
                name = profiles.get(code, {}).get("name", code)
                mv = 0.0
                if not snapshot.empty and "code" in snapshot.columns:
                    match = snapshot[snapshot["code"] == code]
                    if not match.empty and "total_mv" in match.columns:
                        mv = float(match.iloc[0].get("total_mv", 0) or 0)
                stocks.append({"code": code, "name": name, "total_mv": mv})
            stocks.sort(key=lambda x: x["total_mv"], reverse=True)
            return stocks
        except Exception as e:
            logger.warning(f"获取行业成分股失败 [{industry}]: {e}")
            return []

    def _get_stock_name(self, code: str) -> str:
        """获取股票名称"""
        try:
            from engine.data import get_data_engine
            profiles = get_data_engine().get_profiles()
            return profiles.get(code, {}).get("name", code)
        except Exception:
            return code

    def _update_task(self, task_id: str, **kwargs) -> None:
        """更新任务字段"""
        if not kwargs:
            return
        set_parts = []
        values = []
        for k, v in kwargs.items():
            set_parts.append(f"{k} = ?")
            values.append(v)
        values.append(task_id)
        sql = f"UPDATE study.tasks SET {', '.join(set_parts)} WHERE id = ?"
        self._conn.execute(sql, values)

    # ─── 后台执行 ──────────────────────────────────────

    async def _run_task(
        self,
        task_id: str,
        target: str,
        target_type: str,
        depth: str,
        sub_tasks: list[dict],
    ) -> None:
        """后台运行学习任务"""
        try:
            self._update_task(task_id, status="running", progress=0.0)

            if target_type == "stock":
                await self._study_stock(task_id, target, depth)
            else:
                await self._study_industry(task_id, target, depth, sub_tasks)

        except asyncio.CancelledError:
            self._update_task(task_id, status="cancelled")
            logger.info(f"📚 学习任务被取消: {task_id}")
        except Exception as e:
            logger.error(f"📚 学习任务失败 [{task_id}]: {e}")
            self._update_task(task_id, status="failed", error_message=str(e))
        finally:
            self._running_tasks.pop(task_id, None)

    async def _study_stock(self, task_id: str, code: str, depth: str) -> None:
        """学习单只股票"""
        stock_name = self._get_stock_name(code)
        t0 = time.monotonic()

        # Phase 1: 数据采集
        self._update_task(task_id, current_step=f"采集 {stock_name} 数据", progress=0.1)
        data = await self._fetch_stock_data(code)
        logger.info(f"⏱️ 数据采集 [{code}] 耗时 {time.monotonic() - t0:.1f}s")

        # Phase 2: LLM 分析
        self._update_task(task_id, current_step=f"分析 {stock_name}", progress=0.3)
        llm = self._get_llm()
        if not llm:
            raise RuntimeError("LLM 未配置，无法进行学习分析")

        if depth == "quick":
            cognition = await self._quick_analyze(llm, code, stock_name, data)
        else:
            cognition = await self._deep_analyze(llm, code, stock_name, data)

        if not cognition:
            raise RuntimeError(f"LLM 分析 {stock_name} 未返回有效结果")

        # Phase 3: 写入三层记忆
        self._update_task(task_id, current_step=f"写入 {stock_name} 知识", progress=0.7)
        beliefs_count = 0
        beliefs_count += await self._save_to_knowledge_graph(code, stock_name, cognition)
        await self._save_to_agent_memory(code, cognition)
        await self._save_to_rag_store(code, cognition)

        elapsed = time.monotonic() - t0
        summary = cognition.get("key_findings", "分析完成")
        self._update_task(
            task_id,
            status="completed",
            progress=1.0,
            current_step="",
            result_summary=summary,
            beliefs_added=beliefs_count,
            completed_at=datetime.now().isoformat(),
        )
        logger.info(f"⏱️ 学习完成 [{code} {stock_name}] 耗时 {elapsed:.1f}s, {beliefs_count} 条信念")

    async def _study_industry(
        self, task_id: str, industry: str, depth: str, sub_tasks: list[dict]
    ) -> None:
        """学习行业/板块"""
        # Phase 1: 行业整体认知
        self._update_task(task_id, current_step=f"获取 {industry} 行业认知", progress=0.05)

        industry_cognition = {}
        try:
            from engine.industry import get_industry_engine
            ie = get_industry_engine()
            industry_cognition = await ie.analyze(industry)
            if hasattr(industry_cognition, "model_dump"):
                industry_cognition = industry_cognition.model_dump()
            elif not isinstance(industry_cognition, dict):
                industry_cognition = {"raw": str(industry_cognition)}
        except Exception as e:
            logger.warning(f"获取行业认知失败 [{industry}]: {e}")

        # Phase 2: 逐个学习关键个股
        total = len(sub_tasks) if sub_tasks else 1
        total_beliefs = 0

        for i, sub in enumerate(sub_tasks):
            code = sub["code"]
            name = sub.get("name", code)
            progress = 0.1 + 0.8 * (i / total)

            # 更新子任务状态
            sub["status"] = "running"
            self._update_task(
                task_id,
                current_step=f"分析 {name} ({i + 1}/{total})",
                progress=progress,
                sub_tasks=json.dumps(sub_tasks),
            )

            try:
                data = await self._fetch_stock_data(code)
                llm = self._get_llm()
                if not llm:
                    sub["status"] = "failed"
                    continue

                if depth == "quick":
                    cognition = await self._quick_analyze(llm, code, name, data)
                else:
                    cognition = await self._deep_analyze(llm, code, name, data)

                if cognition:
                    bc = await self._save_to_knowledge_graph(code, name, cognition)
                    await self._save_to_agent_memory(code, cognition)
                    await self._save_to_rag_store(code, cognition)
                    total_beliefs += bc
                    sub["status"] = "completed"
                    sub["beliefs"] = bc
                else:
                    sub["status"] = "failed"

            except Exception as e:
                logger.warning(f"学习个股失败 [{code}]: {e}")
                sub["status"] = "failed"
                sub["error"] = str(e)

        # Phase 3: 完成
        self._update_task(
            task_id,
            status="completed",
            progress=1.0,
            current_step="",
            result_summary=f"行业 {industry} 学习完成，分析了 {total} 只关键个股",
            beliefs_added=total_beliefs,
            sub_tasks=json.dumps(sub_tasks),
            completed_at=datetime.now().isoformat(),
        )
        logger.info(f"📚 行业学习完成 [{industry}] {total} 只个股, {total_beliefs} 条信念")

    # ─── 数据采集 ──────────────────────────────────────

    async def _fetch_stock_data(self, code: str) -> dict:
        """采集个股全维度数据"""
        from engine.arena.data_fetcher import DataFetcher
        fetcher = DataFetcher()

        # 基础数据 (fundamental + info + quant)
        all_data = await fetcher.fetch_all(code)

        # 补充产业链认知
        industry_data = {}
        try:
            from engine.industry import get_industry_engine
            ie = get_industry_engine()
            result = await ie.analyze(code)
            if hasattr(result, "model_dump"):
                industry_data = result.model_dump()
            elif isinstance(result, dict):
                industry_data = result
            else:
                industry_data = {"raw": str(result)}
        except Exception as e:
            logger.warning(f"获取产业链认知失败 [{code}]: {e}")

        all_data["industry"] = industry_data
        return all_data

    # ─── LLM 分析 ──────────────────────────────────────

    async def _quick_analyze(
        self, llm: BaseLLMProvider, code: str, stock_name: str, data: dict
    ) -> dict:
        """单次 LLM 调用分析"""
        prompt = QUICK_ANALYZE_PROMPT.format(
            stock_name=stock_name,
            code=code,
            fundamental=json.dumps(data.get("fundamental", {}), ensure_ascii=False, default=str),
            quant=json.dumps(data.get("quant", {}), ensure_ascii=False, default=str),
            info=json.dumps(data.get("info", {}), ensure_ascii=False, default=str),
            industry=json.dumps(data.get("industry", {}), ensure_ascii=False, default=str),
        )

        # 流式收集（保持链路活跃）
        chunks: list[str] = []
        async for token in llm.chat_stream([ChatMessage("user", prompt)]):
            chunks.append(token)
        raw = "".join(chunks)

        return _parse_json_from_llm(raw)

    async def _deep_analyze(
        self, llm: BaseLLMProvider, code: str, stock_name: str, data: dict
    ) -> dict:
        """多轮 LLM 分析（基本面 → 技术面 → 资讯面 → 综合）"""
        fundamental_str = json.dumps(data.get("fundamental", {}), ensure_ascii=False, default=str)
        quant_str = json.dumps(data.get("quant", {}), ensure_ascii=False, default=str)
        info_str = json.dumps(data.get("info", {}), ensure_ascii=False, default=str)
        industry_str = json.dumps(data.get("industry", {}), ensure_ascii=False, default=str)

        # Round 1: 基本面
        prompt1 = DEEP_FUNDAMENTAL_PROMPT.format(
            stock_name=stock_name, code=code, fundamental=fundamental_str, quant=quant_str
        )
        chunks: list[str] = []
        async for token in llm.chat_stream([ChatMessage("user", prompt1)]):
            chunks.append(token)
        fundamental_analysis = _parse_json_from_llm("".join(chunks))

        # Round 2: 技术面
        prompt2 = DEEP_TECHNICAL_PROMPT.format(
            stock_name=stock_name, code=code, quant=quant_str, fundamental=fundamental_str
        )
        chunks = []
        async for token in llm.chat_stream([ChatMessage("user", prompt2)]):
            chunks.append(token)
        technical_analysis = _parse_json_from_llm("".join(chunks))

        # Round 3: 资讯面
        prompt3 = DEEP_INFO_PROMPT.format(
            stock_name=stock_name, code=code, info=info_str
        )
        chunks = []
        async for token in llm.chat_stream([ChatMessage("user", prompt3)]):
            chunks.append(token)
        info_analysis = _parse_json_from_llm("".join(chunks))

        # Round 4: 综合研判
        prompt4 = DEEP_SYNTHESIS_PROMPT.format(
            stock_name=stock_name,
            code=code,
            fundamental_analysis=json.dumps(fundamental_analysis, ensure_ascii=False, default=str),
            technical_analysis=json.dumps(technical_analysis, ensure_ascii=False, default=str),
            info_analysis=json.dumps(info_analysis, ensure_ascii=False, default=str),
            industry=industry_str,
        )
        chunks = []
        async for token in llm.chat_stream([ChatMessage("user", prompt4)]):
            chunks.append(token)
        synthesis = _parse_json_from_llm("".join(chunks))

        # 合并所有信念
        all_beliefs = []
        for analysis in [fundamental_analysis, technical_analysis, info_analysis, synthesis]:
            all_beliefs.extend(analysis.get("beliefs", []))
        synthesis["beliefs"] = all_beliefs

        # 如果 synthesis 缺少 data_summary 等字段，从各轮补充
        if not synthesis.get("data_summary"):
            synthesis["data_summary"] = fundamental_analysis.get("summary", "")
        if not synthesis.get("quant_summary"):
            synthesis["quant_summary"] = technical_analysis.get("summary", "")
        if not synthesis.get("info_summary"):
            synthesis["info_summary"] = info_analysis.get("summary", "")

        return synthesis

    # ─── 三层记忆写入 ──────────────────────────────────

    async def _save_to_knowledge_graph(self, code: str, stock_name: str, cognition: dict) -> int:
        """写入 Knowledge Graph，返回新增信念数"""
        try:
            from engine.expert.knowledge_graph import KnowledgeGraph
            from engine.expert.schemas import (
                StockNode, SectorNode, EventNode, BeliefNode, StanceNode, GraphEdge
            )

            kg_path = str(Path(settings.datasource.data_dir) / "expert_kg.json")
            graph = KnowledgeGraph(kg_path)

            # 添加/更新 StockNode
            # 检查是否已有该股票节点
            existing_stock_id = None
            for nid in graph.graph.nodes():
                ndata = graph.graph.nodes[nid]
                if ndata.get("type") == "stock" and ndata.get("code") == code:
                    existing_stock_id = nid
                    break

            if not existing_stock_id:
                stock_node = StockNode(code=code, name=stock_name)
                await graph.add_node(stock_node)
                stock_id = stock_node.id
            else:
                stock_id = existing_stock_id
                # 更新 updated_at
                graph.graph.nodes[stock_id]["updated_at"] = datetime.now().isoformat()

            beliefs_count = 0

            # 添加 BeliefNode（persona=None → 所有专家共享，用 "study" 标识）
            for b in cognition.get("beliefs", []):
                content = b.get("content", "")
                confidence = b.get("confidence", 0.5)
                if not content:
                    continue
                belief = BeliefNode(
                    content=f"[{stock_name}] {content}",
                    confidence=float(confidence),
                    persona="rag",  # 所有专家共享
                )
                await graph.add_node(belief)
                # 添加 stock → belief 关系
                await graph.add_edge(GraphEdge(
                    source_id=stock_id,
                    target_id=belief.id,
                    relation="researched",
                    reason=f"study学习: {b.get('category', '')}",
                ))
                beliefs_count += 1

            # 添加 StanceNode
            stance = cognition.get("stance", "neutral")
            stance_confidence = cognition.get("stance_confidence", 0.5)
            stance_node = StanceNode(
                target=code,
                signal=stance if stance in ("bullish", "bearish", "neutral") else "neutral",
                score=float(stance_confidence) if stance == "bullish" else -float(stance_confidence) if stance == "bearish" else 0.0,
                confidence=float(stance_confidence),
            )
            await graph.add_node(stance_node)

            # 添加 entity 关系
            for ent in cognition.get("entities", []):
                ent_type = ent.get("type", "")
                ent_name = ent.get("name", "")
                if not ent_name:
                    continue
                if ent_type == "sector":
                    sector_node = SectorNode(name=ent_name, category="industry")
                    await graph.add_node(sector_node)
                    await graph.add_edge(GraphEdge(
                        source_id=stock_id,
                        target_id=sector_node.id,
                        relation="belongs_to",
                    ))
                elif ent_type == "event":
                    event_node = EventNode(
                        name=ent_name,
                        date=datetime.now().strftime("%Y-%m-%d"),
                        description=", ".join(ent.get("relations", [])),
                    )
                    await graph.add_node(event_node)
                    await graph.add_edge(GraphEdge(
                        source_id=stock_id,
                        target_id=event_node.id,
                        relation="influenced_by",
                    ))

            # 持久化
            await graph.save()
            logger.info(f"📚 Knowledge Graph 写入: {code} {stock_name}, {beliefs_count} 条信念")
            return beliefs_count

        except Exception as e:
            logger.error(f"写入 Knowledge Graph 失败 [{code}]: {e}")
            return 0

    async def _save_to_agent_memory(self, code: str, cognition: dict) -> None:
        """写入 ChromaDB Agent Memory — 按角色存储"""
        try:
            from engine.arena.memory import AgentMemory
            memory = AgentMemory(persist_dir=str(settings.chromadb.persist_dir))

            role_mapping = {
                "data": "data_summary",
                "quant": "quant_summary",
                "info": "info_summary",
                "industry": "industry_summary",
            }

            for role, key in role_mapping.items():
                content = cognition.get(key, "")
                if not content:
                    continue
                memory.store(
                    agent_role=role,
                    target=code,
                    content=content,
                    metadata={"source": "study", "depth": "auto"},
                )

            # 也存一份综合的到 rag 角色
            key_findings = cognition.get("key_findings", "")
            if key_findings:
                memory.store(
                    agent_role="rag",
                    target=code,
                    content=key_findings,
                    metadata={"source": "study"},
                )

            logger.info(f"📚 Agent Memory 写入: {code}")
        except Exception as e:
            logger.error(f"写入 Agent Memory 失败 [{code}]: {e}")

    async def _save_to_rag_store(self, code: str, cognition: dict) -> None:
        """写入 RAG Store"""
        try:
            from engine.arena.rag.store import RAGStore
            from engine.arena.rag.schemas import ReportRecord

            store = RAGStore(persist_dir=str(settings.rag.persist_dir))
            summary = cognition.get("key_findings", "")
            if not summary:
                return

            stance = cognition.get("stance", "neutral")
            confidence = cognition.get("stance_confidence", 0.5)

            record = ReportRecord(
                report_id=RAGStore.make_report_id(code, "study"),
                code=code,
                summary=summary,
                signal=stance if stance in ("bullish", "bearish", "neutral") else "neutral",
                score=float(confidence),
                report_type="study",
                created_at=datetime.now(),
            )
            store.store(record)
            logger.info(f"📚 RAG Store 写入: {code}")
        except Exception as e:
            logger.error(f"写入 RAG Store 失败 [{code}]: {e}")


# ─── 单例 ───────────────────────────────────────────
_study_engine: StudyEngine | None = None


def get_study_engine() -> StudyEngine:
    """获取 StudyEngine 单例"""
    global _study_engine
    if _study_engine is None:
        _study_engine = StudyEngine()
    return _study_engine
