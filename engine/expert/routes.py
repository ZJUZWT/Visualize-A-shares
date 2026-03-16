"""投资专家 Agent 路由 — 多专家统一入口"""

import json
import uuid
from datetime import datetime
from pathlib import Path

import duckdb
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from loguru import logger

from config import settings, DB_PATH, DATA_DIR
from expert.agent import ExpertAgent
from expert.engine_experts import EngineExpert, ExpertType, get_expert_profiles
from expert.schemas import ExpertChatRequest
from expert.tools import ExpertTools
from llm.config import llm_settings
from llm.providers import LLMProviderFactory

router = APIRouter(prefix="/api/v1/expert", tags=["expert"])

# 全局 Agent 实例
_expert_agent: ExpertAgent | None = None
_engine_experts: dict[str, EngineExpert] = {}

# 专家对话历史使用独立数据库，避免与 stockterrain.duckdb 的 WAL 冲突
EXPERT_DB_PATH = DATA_DIR / "expert_chat.duckdb"


def _get_db():
    return duckdb.connect(str(EXPERT_DB_PATH))


async def _init_db():
    """初始化 DuckDB expert schema 和表"""
    con = None
    try:
        con = _get_db()
        con.execute("CREATE SCHEMA IF NOT EXISTS expert")
        con.execute("""
            CREATE TABLE IF NOT EXISTS expert.conversation_log (
                id VARCHAR PRIMARY KEY,
                expert_type VARCHAR DEFAULT 'rag',
                user_message VARCHAR,
                expert_reply VARCHAR,
                belief_changes JSON,
                tools_used JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        logger.info("expert.conversation_log 表初始化完成")
    except Exception as e:
        logger.error(f"expert DB 初始化失败: {e}")
    finally:
        if con:
            con.close()

    # 初始化 RAG Agent 实例
    global _expert_agent
    try:
        from data_engine import get_data_engine
        from cluster_engine import get_cluster_engine

        data_engine = get_data_engine()
        cluster_engine = get_cluster_engine()

        # 复用 .env 全局 LLM 配置
        llm_provider = LLMProviderFactory.create(llm_settings) if llm_settings.api_key else None

        tools = ExpertTools(
            data_engine=data_engine,
            cluster_engine=cluster_engine,
            llm_engine=llm_provider,
        )

        kg_path = str(DATA_DIR / "expert_kg.json")
        Path(kg_path).parent.mkdir(parents=True, exist_ok=True)

        chromadb_dir = str(settings.chromadb.persist_dir)

        _expert_agent = ExpertAgent(tools, kg_path=kg_path, chromadb_dir=chromadb_dir)
        logger.info("投资专家 Agent 已初始化")

    except Exception as e:
        logger.error(f"投资专家 Agent 初始化失败: {e}")

    # 初始化 4 个引擎专家
    global _engine_experts
    try:
        llm_provider = LLMProviderFactory.create(llm_settings) if llm_settings.api_key else None
        for expert_type in ("data", "quant", "info", "industry"):
            _engine_experts[expert_type] = EngineExpert(expert_type, llm_provider)
        logger.info(f"引擎专家已初始化: {list(_engine_experts.keys())}")
    except Exception as e:
        logger.error(f"引擎专家初始化失败: {e}")


def get_expert_agent() -> ExpertAgent:
    """获取 RAG Agent 实例"""
    if _expert_agent is None:
        raise RuntimeError("Expert Agent 未初始化")
    return _expert_agent


# ── 多专家统一入口 ──────────────────────────────────────


@router.get("/profiles")
async def list_expert_profiles():
    """返回所有专家配置信息（前端用于渲染专家选择器）"""
    return get_expert_profiles()


@router.post("/chat/{expert_type}")
async def expert_chat_by_type(expert_type: ExpertType, req: ExpertChatRequest):
    """与指定类型的专家对话（SSE 流式）"""
    if expert_type == "rag":
        return await _rag_chat(req)
    
    expert = _engine_experts.get(expert_type)
    if not expert:
        return StreamingResponse(
            _error_stream(f"专家类型 {expert_type} 未初始化"),
            media_type="text/event-stream",
        )

    async def event_stream():
        full_reply = ""
        tools_used = []
        try:
            async for event in expert.chat(req.message):
                evt_type = event["event"]
                if evt_type == "reply_complete":
                    full_reply = event["data"].get("full_text", "")
                elif evt_type == "tool_call":
                    tools_used.append(event["data"].get("action", ""))
                yield f"event: {evt_type}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"{expert_type} expert chat 错误: {e}")
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"
            return

        # 写入 DuckDB 对话历史
        _save_conversation(expert_type, req.message, full_reply, [], tools_used)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/chat")
async def expert_chat(req: ExpertChatRequest):
    """与 RAG 专家 Agent 对话（SSE 流式）— 兼容旧接口"""
    return await _rag_chat(req)


async def _rag_chat(req: ExpertChatRequest):
    """RAG 专家对话"""
    agent = get_expert_agent()

    async def event_stream():
        full_reply = ""
        belief_changes = []
        tools_used = []
        try:
            async for event in agent.chat(req.message):
                evt_type = event["event"]
                if evt_type == "reply_complete":
                    full_reply = event["data"].get("full_text", "")
                elif evt_type == "tool_call":
                    tools_used.append(event["data"].get("action", ""))
                elif evt_type == "belief_updated":
                    belief_changes.append(event["data"])
                yield f"event: {evt_type}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"expert chat 错误: {e}")
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"
            return

        _save_conversation("rag", req.message, full_reply, belief_changes, tools_used)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


async def _error_stream(message: str):
    yield f"event: error\ndata: {json.dumps({'message': message}, ensure_ascii=False)}\n\n"


def _save_conversation(
    expert_type: str, user_message: str, expert_reply: str,
    belief_changes: list, tools_used: list,
):
    """写入 DuckDB 对话历史"""
    con = None
    try:
        con = _get_db()
        # 兼容旧表：如果 expert_type 列不存在则添加
        try:
            con.execute("ALTER TABLE expert.conversation_log ADD COLUMN expert_type VARCHAR DEFAULT 'rag'")
            logger.info("迁移: expert.conversation_log 添加 expert_type 列")
        except Exception:
            pass  # 列已存在
        con.execute(
            """INSERT INTO expert.conversation_log
               (id, expert_type, user_message, expert_reply, belief_changes, tools_used, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                str(uuid.uuid4()),
                expert_type,
                user_message,
                expert_reply,
                json.dumps(belief_changes, ensure_ascii=False),
                json.dumps(tools_used, ensure_ascii=False),
                datetime.now(),
            ],
        )
    except Exception as e:
        logger.warning(f"对话历史写入失败: {e}")
    finally:
        if con:
            con.close()


@router.get("/graph")
async def get_graph():
    """返回当前知识图谱（JSON）"""
    agent = get_expert_agent()
    return agent._graph.to_dict()


@router.get("/beliefs")
async def get_beliefs():
    """获取当前信念列表"""
    agent = get_expert_agent()
    return {"beliefs": agent.get_beliefs()}


@router.get("/stances")
async def get_stances():
    """获取当前立场列表"""
    agent = get_expert_agent()
    return {"stances": agent.get_stances()}


@router.get("/history")
async def get_history(limit: int = 20):
    """返回对话历史（从 DuckDB 按时间倒序）"""
    con = None
    try:
        con = _get_db()
        rows = con.execute(
            "SELECT id, user_message, expert_reply, belief_changes, tools_used, created_at "
            "FROM expert.conversation_log ORDER BY created_at DESC LIMIT ?",
            [limit],
        ).fetchall()
        return [
            {
                "id": r[0],
                "user_message": r[1],
                "expert_reply": r[2],
                "belief_changes": r[3],
                "tools_used": r[4],
                "created_at": str(r[5]),
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"获取对话历史失败: {e}")
        return []
    finally:
        if con:
            con.close()


@router.get("/knowledge-graph/stats")
async def get_kg_stats():
    """获取知识图谱统计"""
    agent = get_expert_agent()
    return agent._graph.stats()
