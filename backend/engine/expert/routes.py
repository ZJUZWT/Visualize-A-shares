"""投资专家 Agent 路由 — 多专家统一入口 + Session 管理"""

import json
import uuid
from datetime import datetime
from pathlib import Path

import duckdb
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from loguru import logger

from config import settings, DB_PATH, DATA_DIR
from engine.expert.agent import ExpertAgent
from engine.expert.engine_experts import EngineExpert, ExpertType, get_expert_profiles
from engine.expert.schemas import ExpertChatRequest, SessionCreateRequest, ScheduledTaskRequest
from engine.expert.scheduler import ScheduledTaskManager
from engine.expert.tools import ExpertTools
from engine.expert.tool_tracker import ToolOutcomeTracker
from engine.expert.user_profile import UserProfileTracker
from llm.config import llm_settings
from llm.providers import LLMProviderFactory

router = APIRouter(prefix="/api/v1/expert", tags=["expert"])

# 全局 Agent 实例
_expert_agent: ExpertAgent | None = None
_engine_experts: dict[str, EngineExpert] = {}
_tool_tracker: ToolOutcomeTracker | None = None
_user_profile_tracker: UserProfileTracker | None = None
_task_manager: ScheduledTaskManager | None = None

# WebSocket 通知客户端集合
_ws_notify_clients: set[WebSocket] = set()

# 专家对话历史使用独立数据库，避免与 stockterrain.duckdb 的 WAL 冲突
EXPERT_DB_PATH = DATA_DIR / "expert_chat.duckdb"

# 最近 N 轮对话注入 LLM 上下文
MAX_CONTEXT_TURNS = 10


def _get_db():
    return duckdb.connect(str(EXPERT_DB_PATH))


async def _init_db():
    """初始化 DuckDB expert schema 和表"""
    con = None
    try:
        con = _get_db()
        con.execute("CREATE SCHEMA IF NOT EXISTS expert")

        # Session 表
        con.execute("""
            CREATE TABLE IF NOT EXISTS expert.sessions (
                id VARCHAR PRIMARY KEY,
                expert_type VARCHAR NOT NULL DEFAULT 'rag',
                title VARCHAR NOT NULL DEFAULT '新对话',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 对话消息表（每条消息一行，替代旧的 conversation_log）
        con.execute("""
            CREATE TABLE IF NOT EXISTS expert.messages (
                id VARCHAR PRIMARY KEY,
                session_id VARCHAR NOT NULL,
                role VARCHAR NOT NULL,
                content VARCHAR NOT NULL DEFAULT '',
                thinking JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 保留旧表兼容
        con.execute("""
            CREATE TABLE IF NOT EXISTS expert.conversation_log (
                id VARCHAR PRIMARY KEY,
                expert_type VARCHAR DEFAULT 'rag',
                session_id VARCHAR,
                user_message VARCHAR,
                expert_reply VARCHAR,
                belief_changes JSON,
                tools_used JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        logger.info("expert.sessions + expert.messages 表初始化完成")
    except Exception as e:
        logger.error(f"expert DB 初始化失败: {e}")
    finally:
        if con:
            con.close()

    # 初始化 RAG Agent 实例
    global _expert_agent
    try:
        from engine.data import get_data_engine
        from engine.cluster import get_cluster_engine

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

    # 初始化工具使用追踪器
    global _tool_tracker
    _tool_tracker = ToolOutcomeTracker(str(EXPERT_DB_PATH))
    logger.info("ToolOutcomeTracker 已初始化")

    # 初始化用户偏好追踪器
    global _user_profile_tracker
    _user_profile_tracker = UserProfileTracker(str(EXPERT_DB_PATH))
    logger.info("UserProfileTracker 已初始化")

    # 初始化定时任务管理器
    global _task_manager
    _task_manager = ScheduledTaskManager(
        db_path=str(EXPERT_DB_PATH),
        agent=_expert_agent,
        engine_experts=_engine_experts,
        on_complete=_broadcast_task_complete,
    )
    _task_manager.start_scheduler()
    logger.info("ScheduledTaskManager 已初始化")


def get_expert_agent() -> ExpertAgent:
    """获取 RAG Agent 实例"""
    if _expert_agent is None:
        raise RuntimeError("Expert Agent 未初始化")
    return _expert_agent


def get_tool_tracker() -> ToolOutcomeTracker | None:
    """获取工具使用追踪器"""
    return _tool_tracker


def get_user_profile_tracker() -> UserProfileTracker | None:
    """获取用户偏好追踪器"""
    return _user_profile_tracker


# ══════════════════════════════════════════════════════════
# Session CRUD
# ══════════════════════════════════════════════════════════


@router.get("/sessions")
async def list_sessions(expert_type: str = Query(default=None)):
    """列出所有 session（可按 expert_type 过滤）"""
    con = None
    try:
        con = _get_db()
        if expert_type:
            rows = con.execute(
                "SELECT s.id, s.expert_type, s.title, s.created_at, s.updated_at, "
                "(SELECT COUNT(*) FROM expert.messages m WHERE m.session_id = s.id) as msg_count "
                "FROM expert.sessions s WHERE s.expert_type = ? ORDER BY s.updated_at DESC",
                [expert_type],
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT s.id, s.expert_type, s.title, s.created_at, s.updated_at, "
                "(SELECT COUNT(*) FROM expert.messages m WHERE m.session_id = s.id) as msg_count "
                "FROM expert.sessions s ORDER BY s.updated_at DESC",
            ).fetchall()
        return [
            {"id": r[0], "expert_type": r[1], "title": r[2],
             "created_at": str(r[3]), "updated_at": str(r[4]), "message_count": r[5]}
            for r in rows
        ]
    except Exception as e:
        logger.error(f"获取 session 列表失败: {e}")
        return []
    finally:
        if con:
            con.close()


@router.post("/sessions")
async def create_session(req: SessionCreateRequest):
    """创建新 session（接收 JSON body: {expert_type, title}）"""
    con = None
    sid = str(uuid.uuid4())
    expert_type = req.expert_type
    title = req.title
    try:
        con = _get_db()
        now = datetime.now()
        con.execute(
            "INSERT INTO expert.sessions (id, expert_type, title, created_at, updated_at) VALUES (?,?,?,?,?)",
            [sid, expert_type, title, now, now],
        )
        return {"id": sid, "expert_type": expert_type, "title": title,
                "created_at": now.isoformat(), "updated_at": now.isoformat(), "message_count": 0}
    except Exception as e:
        logger.error(f"创建 session 失败: {e}")
        return {"error": str(e)}
    finally:
        if con:
            con.close()


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除 session 及其所有消息"""
    con = None
    try:
        con = _get_db()
        con.execute("DELETE FROM expert.messages WHERE session_id = ?", [session_id])
        con.execute("DELETE FROM expert.sessions WHERE id = ?", [session_id])
        return {"ok": True}
    except Exception as e:
        logger.error(f"删除 session 失败: {e}")
        return {"error": str(e)}
    finally:
        if con:
            con.close()


@router.patch("/sessions/{session_id}")
async def update_session_title(session_id: str, title: str = ""):
    """更新 session 标题"""
    con = None
    try:
        con = _get_db()
        con.execute(
            "UPDATE expert.sessions SET title = ?, updated_at = ? WHERE id = ?",
            [title, datetime.now(), session_id],
        )
        return {"ok": True}
    except Exception as e:
        logger.error(f"更新 session 失败: {e}")
        return {"error": str(e)}
    finally:
        if con:
            con.close()


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    """获取指定 session 的所有消息（按时间正序）"""
    con = None
    try:
        con = _get_db()
        rows = con.execute(
            "SELECT id, role, content, thinking, created_at "
            "FROM expert.messages WHERE session_id = ? ORDER BY created_at ASC",
            [session_id],
        ).fetchall()
        return [
            {"id": r[0], "role": r[1], "content": r[2],
             "thinking": json.loads(r[3]) if r[3] else [],
             "created_at": str(r[4])}
            for r in rows
        ]
    except Exception as e:
        logger.error(f"获取 session 消息失败: {e}")
        return []
    finally:
        if con:
            con.close()


@router.post("/sessions/{session_id}/messages/save-user")
async def save_user_message(session_id: str, body: dict):
    """前端发送时立即将用户消息写入 DB（确保 session message_count 及时更新）"""
    content = body.get("content", "")
    if not content:
        return {"ok": False, "error": "content is empty"}
    _save_message(session_id, "user", content)
    _auto_title(session_id, content)
    return {"ok": True}


def _get_session_history(session_id: str, limit: int = MAX_CONTEXT_TURNS) -> list[dict]:
    """获取指定 session 的最近 N 轮对话（用于注入 LLM 上下文）"""
    if not session_id:
        return []
    con = None
    try:
        con = _get_db()
        rows = con.execute(
            "SELECT role, content FROM expert.messages "
            "WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            [session_id, limit * 2],  # user+expert 各一条 = 1轮
        ).fetchall()
        # 逆序回来（最旧在前）
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]
    except Exception as e:
        logger.debug(f"获取 session 历史失败: {e}")
        return []
    finally:
        if con:
            con.close()


def _save_message(session_id: str, role: str, content: str, thinking: list | None = None):
    """将消息写入 messages 表"""
    if not session_id:
        return
    con = None
    try:
        con = _get_db()
        con.execute(
            "INSERT INTO expert.messages (id, session_id, role, content, thinking, created_at) "
            "VALUES (?,?,?,?,?,?)",
            [str(uuid.uuid4()), session_id, role, content,
             json.dumps(thinking or [], ensure_ascii=False), datetime.now()],
        )
        con.execute(
            "UPDATE expert.sessions SET updated_at = ? WHERE id = ?",
            [datetime.now(), session_id],
        )
    except Exception as e:
        logger.warning(f"消息写入失败: {e}")
    finally:
        if con:
            con.close()


def _auto_title(session_id: str, user_message: str):
    """首条消息时自动设置 session 标题（取前 30 字）"""
    con = None
    try:
        con = _get_db()
        count = con.execute(
            "SELECT COUNT(*) FROM expert.messages WHERE session_id = ?", [session_id]
        ).fetchone()[0]
        if count <= 2:  # 刚存入 user + expert 两条
            title = user_message[:30].replace("\n", " ").strip()
            if len(user_message) > 30:
                title += "..."
            con.execute(
                "UPDATE expert.sessions SET title = ? WHERE id = ?",
                [title, session_id],
            )
    except Exception:
        pass
    finally:
        if con:
            con.close()


# ══════════════════════════════════════════════════════════
# 多专家统一入口
# ══════════════════════════════════════════════════════════


@router.get("/profiles")
async def list_expert_profiles():
    """返回所有专家配置信息（前端用于渲染专家选择器）"""
    return get_expert_profiles()


@router.post("/chat/{expert_type}")
async def expert_chat_by_type(expert_type: ExpertType, req: ExpertChatRequest):
    """与指定类型的专家对话（SSE 流式）"""
    if expert_type == "rag":
        return await _rag_chat(req)

    # 短线专家复用 RAG Agent，但使用 short_term 人格
    if expert_type == "short_term":
        return await _rag_chat(req, persona="short_term")

    expert = _engine_experts.get(expert_type)
    if not expert:
        return StreamingResponse(
            _error_stream(f"专家类型 {expert_type} 未初始化"),
            media_type="text/event-stream",
        )

    # 确保有 session
    session_id = req.session_id or ""
    history = _get_session_history(session_id) if session_id else []

    async def event_stream():
        full_reply = ""
        tools_used = []
        thinking_items = []
        try:
            async for event in expert.chat(
                req.message, history=history,
                deep_think=req.deep_think, max_rounds=req.max_rounds,
            ):
                evt_type = event["event"]
                if evt_type == "reply_complete":
                    full_reply = event["data"].get("full_text", "")
                elif evt_type == "tool_call":
                    tools_used.append(event["data"].get("action", ""))
                    thinking_items.append({"type": "tool_call", "data": event["data"], "status": "pending"})
                elif evt_type == "tool_result":
                    # 将 tool_result 合并到对应的 tool_call 上（更新 status）
                    result_data = event["data"]
                    matched = False
                    for ti in reversed(thinking_items):
                        if (ti["type"] == "tool_call"
                            and ti.get("status") == "pending"
                            and ti["data"].get("engine") == result_data.get("engine")
                            and ti["data"].get("action") == result_data.get("action")):
                            ti["status"] = "error" if result_data.get("hasError") else "done"
                            ti["result"] = result_data
                            matched = True
                            break
                    if not matched:
                        thinking_items.append({"type": "tool_result", "data": result_data})
                elif evt_type == "graph_recall":
                    thinking_items.append({"type": "graph_recall", "data": event["data"]})
                elif evt_type == "thinking_round":
                    thinking_items.append({"type": "thinking_round", "data": event["data"]})
                elif evt_type == "belief_updated":
                    thinking_items.append({"type": "belief_updated", "data": event["data"]})
                yield f"event: {evt_type}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"{expert_type} expert chat 错误: {e}")
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"
            return

        # 存入 session 消息（用户消息已由前端 save-user 接口写入，此处只存 expert 回复）
        if session_id:
            _save_message(session_id, "expert", full_reply, thinking_items)
            _auto_title(session_id, req.message)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/chat")
async def expert_chat(req: ExpertChatRequest):
    """与 RAG 专家 Agent 对话（SSE 流式）— 兼容旧接口"""
    return await _rag_chat(req)


async def _rag_chat(req: ExpertChatRequest, persona: str = "rag"):
    """RAG 专家对话"""
    agent = get_expert_agent()
    session_id = req.session_id or ""
    history = _get_session_history(session_id) if session_id else []

    async def event_stream():
        full_reply = ""
        belief_changes = []
        tools_used = []
        thinking_items = []
        try:
            async for event in agent.chat(
                req.message, history=history, persona=persona,
                deep_think=req.deep_think, max_rounds=req.max_rounds,
            ):
                evt_type = event["event"]
                if evt_type == "reply_complete":
                    full_reply = event["data"].get("full_text", "")
                elif evt_type == "tool_call":
                    tools_used.append(event["data"].get("action", ""))
                    thinking_items.append({"type": "tool_call", "data": event["data"], "status": "pending"})
                elif evt_type == "tool_result":
                    # 将 tool_result 合并到对应的 tool_call 上（更新 status）
                    result_data = event["data"]
                    matched = False
                    for ti in reversed(thinking_items):
                        if (ti["type"] == "tool_call"
                            and ti.get("status") == "pending"
                            and ti["data"].get("engine") == result_data.get("engine")
                            and ti["data"].get("action") == result_data.get("action")):
                            ti["status"] = "error" if result_data.get("hasError") else "done"
                            ti["result"] = result_data
                            matched = True
                            break
                    if not matched:
                        thinking_items.append({"type": "tool_result", "data": result_data})
                elif evt_type == "belief_updated":
                    belief_changes.append(event["data"])
                    thinking_items.append({"type": "belief_updated", "data": event["data"]})
                elif evt_type == "graph_recall":
                    thinking_items.append({"type": "graph_recall", "data": event["data"]})
                yield f"event: {evt_type}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"expert chat 错误: {e}")
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"
            return

        # 存入 session 消息（用户消息已由前端 save-user 接口写入，此处只存 expert 回复）
        if session_id:
            _save_message(session_id, "expert", full_reply, thinking_items)
            _auto_title(session_id, req.message)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


async def _error_stream(message: str):
    yield f"event: error\ndata: {json.dumps({'message': message}, ensure_ascii=False)}\n\n"


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
    """返回对话历史（兼容旧接口）"""
    con = None
    try:
        con = _get_db()
        rows = con.execute(
            "SELECT id, user_message, expert_reply, belief_changes, tools_used, created_at "
            "FROM expert.conversation_log ORDER BY created_at DESC LIMIT ?",
            [limit],
        ).fetchall()
        return [
            {"id": r[0], "user_message": r[1], "expert_reply": r[2],
             "belief_changes": r[3], "tools_used": r[4], "created_at": str(r[5])}
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


# ══════════════════════════════════════════════════════════
# 定时任务调度
# ══════════════════════════════════════════════════════════


def get_task_manager() -> ScheduledTaskManager | None:
    return _task_manager


async def _broadcast_task_complete(task_id: str, task_name: str, full_text: str):
    """任务完成时通过 WebSocket 广播通知"""
    import json as _json
    msg = _json.dumps({
        "type": "task_completed",
        "task_id": task_id,
        "task_name": task_name,
        "summary": full_text[:200] if full_text else "",
    }, ensure_ascii=False)

    dead: list[WebSocket] = []
    for ws in _ws_notify_clients:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_notify_clients.discard(ws)


@router.websocket("/ws/notifications")
async def ws_notifications(websocket: WebSocket):
    """WebSocket 通知通道 — 推送定时任务完成事件"""
    await websocket.accept()
    _ws_notify_clients.add(websocket)
    logger.info(f"🔔 通知 WebSocket 已连接 (当前 {len(_ws_notify_clients)} 个客户端)")
    try:
        while True:
            # 保持连接活跃（等待客户端 ping 或断连）
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _ws_notify_clients.discard(websocket)
        logger.info(f"🔔 通知 WebSocket 已断开 (剩余 {len(_ws_notify_clients)} 个客户端)")


@router.post("/tasks")
async def create_task(req: ScheduledTaskRequest):
    """创建定时任务"""
    if not _task_manager:
        return {"error": "任务调度器未初始化"}

    session_id = None
    if req.create_session:
        # 自动创建专属 session
        con = None
        try:
            con = _get_db()
            session_id = str(uuid.uuid4())
            now = datetime.now()
            con.execute(
                "INSERT INTO expert.sessions (id, expert_type, title, created_at, updated_at) VALUES (?,?,?,?,?)",
                [session_id, req.expert_type, f"⏰ {req.name}", now, now],
            )
        except Exception as e:
            logger.error(f"创建任务 session 失败: {e}")
        finally:
            if con:
                con.close()

    task = _task_manager.create_task(
        name=req.name,
        expert_type=req.expert_type,
        persona=req.persona,
        message=req.message,
        cron_expr=req.cron_expr,
        session_id=session_id,
    )
    return task


@router.get("/tasks")
async def list_tasks():
    """列出所有定时任务"""
    if not _task_manager:
        return []
    return _task_manager.list_tasks()


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """删除定时任务"""
    if not _task_manager:
        return {"error": "任务调度器未初始化"}
    _task_manager.delete_task(task_id)
    return {"ok": True}


@router.post("/tasks/{task_id}/pause")
async def pause_task(task_id: str):
    """暂停定时任务"""
    if not _task_manager:
        return {"error": "任务调度器未初始化"}
    _task_manager.pause_task(task_id)
    return {"ok": True}


@router.post("/tasks/{task_id}/resume")
async def resume_task(task_id: str):
    """恢复定时任务"""
    if not _task_manager:
        return {"error": "任务调度器未初始化"}
    _task_manager.resume_task(task_id)
    return {"ok": True}


@router.post("/tasks/{task_id}/run")
async def run_task_now(task_id: str):
    """立即执行一次定时任务"""
    if not _task_manager:
        return {"error": "任务调度器未初始化"}
    try:
        result = await _task_manager.execute_task(task_id)
        return {"ok": True, "result_length": len(result), "summary": result[:300]}
    except Exception as e:
        return {"error": str(e)}
