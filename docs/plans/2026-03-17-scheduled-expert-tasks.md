# 定时专家任务系统 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 用户可以预约定时任务让专家团队自动执行分析（如"每天收盘后帮我看茅台"），结果存入 Session 体系，前端可查看和管理。

**Architecture:** APScheduler (AsyncIOScheduler) 嵌入 FastAPI 事件循环，任务定义持久化到 DuckDB `expert.scheduled_tasks` 表，执行时直接调用 `ExpertAgent.chat()` 收集完整回复，结果写入 Session 体系复用现有对话 UI。前端新增任务管理面板 + WebSocket 通知通道。

**Tech Stack:** APScheduler 3.x (已在 pyproject.toml), DuckDB, FastAPI WebSocket, Zustand, sonner (toast)

---

### Task 1: DuckDB 表 + ScheduledTaskManager 核心类

**Files:**
- Create: `backend/engine/expert/scheduler.py`
- Modify: `backend/engine/expert/routes.py:42-90` (_init_db 中建表)
- Test: `tests/unit/expert/test_scheduler.py`

**Step 1: 在 _init_db 中新增 scheduled_tasks 表**

在 `routes.py` 的 `_init_db()` 函数中，`expert.messages` 建表之后，加:

```python
# 定时任务表
con.execute("""
    CREATE TABLE IF NOT EXISTS expert.scheduled_tasks (
        id VARCHAR PRIMARY KEY,
        name VARCHAR NOT NULL,
        expert_type VARCHAR NOT NULL DEFAULT 'rag',
        persona VARCHAR NOT NULL DEFAULT 'rag',
        message VARCHAR NOT NULL,
        cron_expr VARCHAR NOT NULL,
        session_id VARCHAR,
        status VARCHAR NOT NULL DEFAULT 'active',
        last_run_at TIMESTAMP,
        last_result_summary VARCHAR,
        next_run_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")
```

**Step 2: 写测试 — ScheduledTaskManager CRUD**

```python
# tests/unit/expert/test_scheduler.py
"""定时专家任务系统测试"""
import pytest
import duckdb
from engine.expert.scheduler import ScheduledTaskManager

@pytest.fixture
def manager(tmp_path):
    db_path = str(tmp_path / "test.duckdb")
    m = ScheduledTaskManager(db_path, agent=None, engine_experts={})
    return m

class TestTaskCRUD:
    def test_create_task(self, manager):
        task = manager.create_task(
            name="每日看茅台",
            expert_type="rag",
            message="帮我分析一下贵州茅台今天的走势",
            cron_expr="0 15 * * 1-5",
        )
        assert task["id"]
        assert task["name"] == "每日看茅台"
        assert task["status"] == "active"

    def test_list_tasks(self, manager):
        manager.create_task(name="任务1", expert_type="rag", message="msg1", cron_expr="0 15 * * 1-5")
        manager.create_task(name="任务2", expert_type="short_term", message="msg2", cron_expr="0 9 * * 1-5")
        tasks = manager.list_tasks()
        assert len(tasks) == 2

    def test_delete_task(self, manager):
        task = manager.create_task(name="要删的", expert_type="rag", message="msg", cron_expr="0 15 * * 1-5")
        manager.delete_task(task["id"])
        assert len(manager.list_tasks()) == 0

    def test_pause_resume_task(self, manager):
        task = manager.create_task(name="暂停测试", expert_type="rag", message="msg", cron_expr="0 15 * * 1-5")
        manager.pause_task(task["id"])
        tasks = manager.list_tasks()
        assert tasks[0]["status"] == "paused"
        manager.resume_task(task["id"])
        tasks = manager.list_tasks()
        assert tasks[0]["status"] == "active"

    def test_update_last_run(self, manager):
        task = manager.create_task(name="运行测试", expert_type="rag", message="msg", cron_expr="0 15 * * 1-5")
        manager.update_last_run(task["id"], "茅台今天涨了2%，技术面...")
        tasks = manager.list_tasks()
        assert tasks[0]["last_run_at"] is not None
        assert "茅台" in tasks[0]["last_result_summary"]
```

Run: `pytest tests/unit/expert/test_scheduler.py -v`
Expected: FAIL (module not found)

**Step 3: 实现 ScheduledTaskManager**

```python
# backend/engine/expert/scheduler.py
"""定时专家任务调度系统

基于 APScheduler AsyncIOScheduler，嵌入 FastAPI 事件循环。
任务定义持久化到 DuckDB，执行结果写入 Session 体系。
"""

import uuid
from datetime import datetime
from typing import Any

import duckdb
from loguru import logger


class ScheduledTaskManager:
    """定时任务管理器 — CRUD + 执行"""

    def __init__(self, db_path: str, agent, engine_experts: dict):
        self._db_path = db_path
        self._agent = agent
        self._engine_experts = engine_experts
        self._ensure_table()

    def _get_db(self):
        return duckdb.connect(self._db_path)

    def _ensure_table(self):
        con = self._get_db()
        try:
            con.execute("CREATE SCHEMA IF NOT EXISTS expert")
            con.execute("""
                CREATE TABLE IF NOT EXISTS expert.scheduled_tasks (
                    id VARCHAR PRIMARY KEY,
                    name VARCHAR NOT NULL,
                    expert_type VARCHAR NOT NULL DEFAULT 'rag',
                    persona VARCHAR NOT NULL DEFAULT 'rag',
                    message VARCHAR NOT NULL,
                    cron_expr VARCHAR NOT NULL,
                    session_id VARCHAR,
                    status VARCHAR NOT NULL DEFAULT 'active',
                    last_run_at TIMESTAMP,
                    last_result_summary VARCHAR,
                    next_run_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        finally:
            con.close()

    def create_task(
        self,
        name: str,
        expert_type: str,
        message: str,
        cron_expr: str,
        persona: str = "rag",
        session_id: str | None = None,
    ) -> dict:
        task_id = str(uuid.uuid4())
        now = datetime.now()
        con = self._get_db()
        try:
            con.execute(
                """INSERT INTO expert.scheduled_tasks
                   (id, name, expert_type, persona, message, cron_expr, session_id, status, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                [task_id, name, expert_type, persona, message, cron_expr, session_id, "active", now],
            )
            return {
                "id": task_id, "name": name, "expert_type": expert_type,
                "persona": persona, "message": message, "cron_expr": cron_expr,
                "session_id": session_id, "status": "active",
                "last_run_at": None, "last_result_summary": None,
                "created_at": now.isoformat(),
            }
        finally:
            con.close()

    def list_tasks(self) -> list[dict]:
        con = self._get_db()
        try:
            rows = con.execute(
                "SELECT id, name, expert_type, persona, message, cron_expr, session_id, "
                "status, last_run_at, last_result_summary, next_run_at, created_at "
                "FROM expert.scheduled_tasks ORDER BY created_at DESC"
            ).fetchall()
            cols = ["id", "name", "expert_type", "persona", "message", "cron_expr",
                    "session_id", "status", "last_run_at", "last_result_summary",
                    "next_run_at", "created_at"]
            return [dict(zip(cols, r)) for r in rows]
        finally:
            con.close()

    def delete_task(self, task_id: str):
        con = self._get_db()
        try:
            con.execute("DELETE FROM expert.scheduled_tasks WHERE id = ?", [task_id])
        finally:
            con.close()

    def pause_task(self, task_id: str):
        con = self._get_db()
        try:
            con.execute("UPDATE expert.scheduled_tasks SET status = 'paused' WHERE id = ?", [task_id])
        finally:
            con.close()

    def resume_task(self, task_id: str):
        con = self._get_db()
        try:
            con.execute("UPDATE expert.scheduled_tasks SET status = 'active' WHERE id = ?", [task_id])
        finally:
            con.close()

    def update_last_run(self, task_id: str, result_summary: str):
        con = self._get_db()
        try:
            con.execute(
                "UPDATE expert.scheduled_tasks SET last_run_at = ?, last_result_summary = ? WHERE id = ?",
                [datetime.now(), result_summary[:500], task_id],
            )
        finally:
            con.close()
```

Run: `pytest tests/unit/expert/test_scheduler.py -v`
Expected: 5 PASS

**Step 4: Commit**

```bash
git add backend/engine/expert/scheduler.py tests/unit/expert/test_scheduler.py
git commit -m "feat(scheduler): ScheduledTaskManager CRUD + DuckDB 持久化"
```

---

### Task 2: APScheduler 集成 + 任务执行引擎

**Files:**
- Modify: `backend/engine/expert/scheduler.py` (添加 APScheduler 集成 + execute_task)
- Modify: `backend/engine/expert/routes.py` (添加初始化 + 全局实例)
- Modify: `backend/main.py` (startup/shutdown 钩子)
- Test: `tests/unit/expert/test_scheduler.py` (添加执行测试)

**Step 1: 写测试 — 任务执行**

在 `test_scheduler.py` 追加:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock

class TestTaskExecution:
    @pytest.mark.asyncio
    async def test_execute_task_rag(self, tmp_path):
        """RAG 专家任务执行，收集完整回复"""
        db_path = str(tmp_path / "test.duckdb")

        # Mock agent
        mock_agent = MagicMock()
        async def fake_chat(message, history=None, persona="rag"):
            yield {"event": "reply_token", "data": {"token": "茅台"}}
            yield {"event": "reply_token", "data": {"token": "今天涨了"}}
            yield {"event": "reply_complete", "data": {"full_text": "茅台今天涨了2%"}}
        mock_agent.chat = fake_chat

        manager = ScheduledTaskManager(db_path, agent=mock_agent, engine_experts={})
        task = manager.create_task(
            name="测试任务", expert_type="rag",
            message="分析茅台", cron_expr="0 15 * * 1-5",
        )

        result = await manager.execute_task(task["id"])
        assert "茅台" in result
        tasks = manager.list_tasks()
        assert tasks[0]["last_run_at"] is not None

    @pytest.mark.asyncio
    async def test_execute_task_engine_expert(self, tmp_path):
        """引擎专家任务执行"""
        db_path = str(tmp_path / "test.duckdb")

        mock_expert = MagicMock()
        async def fake_chat(message, history=None):
            yield {"event": "reply_complete", "data": {"full_text": "MACD金叉信号"}}
        mock_expert.chat = fake_chat

        manager = ScheduledTaskManager(
            db_path, agent=None,
            engine_experts={"quant": mock_expert},
        )
        task = manager.create_task(
            name="量化信号", expert_type="quant",
            message="茅台技术面", cron_expr="0 15 * * 1-5",
        )
        result = await manager.execute_task(task["id"])
        assert "MACD" in result
```

**Step 2: 实现 execute_task + APScheduler 集成**

在 `scheduler.py` 中添加:

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

class ScheduledTaskManager:
    # ... 已有 CRUD 代码 ...

    def _init_scheduler(self):
        """初始化 APScheduler（仅在有 agent 时调用）"""
        self._scheduler = AsyncIOScheduler()
        self._scheduler.start()
        logger.info("⏰ APScheduler 已启动")
        # 从 DB 恢复所有 active 任务
        for task in self.list_tasks():
            if task["status"] == "active":
                self._register_job(task)

    def _register_job(self, task: dict):
        """将任务注册到 APScheduler"""
        try:
            trigger = CronTrigger.from_crontab(task["cron_expr"])
            self._scheduler.add_job(
                self._job_wrapper,
                trigger=trigger,
                id=task["id"],
                args=[task["id"]],
                replace_existing=True,
                name=task["name"],
            )
            logger.info(f"⏰ 任务已注册: {task['name']} ({task['cron_expr']})")
        except Exception as e:
            logger.error(f"任务注册失败 [{task['name']}]: {e}")

    def _unregister_job(self, task_id: str):
        """从 APScheduler 移除任务"""
        try:
            if self._scheduler and self._scheduler.get_job(task_id):
                self._scheduler.remove_job(task_id)
        except Exception:
            pass

    async def _job_wrapper(self, task_id: str):
        """APScheduler 调用的 wrapper"""
        logger.info(f"⏰ 定时任务开始执行: {task_id}")
        try:
            result = await self.execute_task(task_id)
            logger.info(f"⏰ 定时任务完成: {task_id}, 结果长度: {len(result)}")
        except Exception as e:
            logger.error(f"⏰ 定时任务失败: {task_id}: {e}")

    async def execute_task(self, task_id: str) -> str:
        """执行一次任务 — 调用专家 chat() 收集完整回复"""
        import time
        start = time.time()

        # 从 DB 读取任务信息
        con = self._get_db()
        try:
            row = con.execute(
                "SELECT expert_type, persona, message, session_id FROM expert.scheduled_tasks WHERE id = ?",
                [task_id]
            ).fetchone()
        finally:
            con.close()

        if not row:
            raise ValueError(f"任务不存在: {task_id}")

        expert_type, persona, message, session_id = row

        # 调用专家
        full_text = ""
        if expert_type in ("rag", "short_term"):
            if not self._agent:
                return "Agent 未初始化"
            async for event in self._agent.chat(message, persona=persona):
                if event.get("event") == "reply_complete":
                    full_text = event["data"]["full_text"]
        else:
            expert = self._engine_experts.get(expert_type)
            if not expert:
                return f"引擎专家 {expert_type} 未初始化"
            async for event in expert.chat(message):
                if event.get("event") == "reply_complete":
                    full_text = event["data"]["full_text"]

        elapsed = time.time() - start
        logger.info(f"⏰ 任务 {task_id} 执行耗时: {elapsed:.1f}s")

        # 如果有 session_id，保存到 session 消息体系
        if session_id:
            self._save_to_session(session_id, message, full_text)

        # 更新任务状态
        summary = full_text[:500] if full_text else "无结果"
        self.update_last_run(task_id, summary)

        # 通知回调（WebSocket 推送，Task 3 实现）
        if self._on_complete:
            await self._on_complete(task_id, full_text)

        return full_text

    def _save_to_session(self, session_id: str, user_msg: str, expert_reply: str):
        """将执行结果存入 Session 消息体系"""
        con = self._get_db()
        try:
            now = datetime.now()
            # 存用户消息
            con.execute(
                "INSERT INTO expert.messages (id, session_id, role, content, created_at) VALUES (?,?,?,?,?)",
                [str(uuid.uuid4()), session_id, "user", f"[⏰ 定时任务] {user_msg}", now],
            )
            # 存专家回复
            con.execute(
                "INSERT INTO expert.messages (id, session_id, role, content, created_at) VALUES (?,?,?,?,?)",
                [str(uuid.uuid4()), session_id, "expert", expert_reply, now],
            )
            # 更新 session 的 updated_at
            con.execute(
                "UPDATE expert.sessions SET updated_at = ? WHERE id = ?", [now, session_id]
            )
        finally:
            con.close()

    def shutdown(self):
        if hasattr(self, '_scheduler') and self._scheduler:
            self._scheduler.shutdown(wait=False)
            logger.info("⏰ APScheduler 已关闭")
```

**Step 3: 在 routes.py 中集成初始化**

在 `_init_db()` 末尾添加 ScheduledTaskManager 初始化，在 `main.py` 的 shutdown 中调用 `shutdown()`。

**Step 4: 测试通过后 Commit**

```bash
git commit -m "feat(scheduler): APScheduler 集成 + execute_task 任务执行引擎"
```

---

### Task 3: REST API + WebSocket 通知

**Files:**
- Modify: `backend/engine/expert/routes.py` (新增 6 个路由 + WS 端点)
- Test: `tests/unit/expert/test_scheduler_routes.py`

**新增路由:**

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/expert/tasks` | 创建定时任务 |
| GET | `/api/v1/expert/tasks` | 列出所有任务 |
| DELETE | `/api/v1/expert/tasks/{id}` | 删除任务 |
| POST | `/api/v1/expert/tasks/{id}/pause` | 暂停任务 |
| POST | `/api/v1/expert/tasks/{id}/resume` | 恢复任务 |
| POST | `/api/v1/expert/tasks/{id}/run` | 立即执行一次 |
| WS | `/api/v1/expert/ws/notifications` | 任务完成通知推送 |

**请求体 (POST /tasks):**

```python
class ScheduledTaskRequest(BaseModel):
    name: str               # "每日看茅台"
    expert_type: str = "rag" # rag / short_term / data / quant / info / industry
    persona: str = "rag"     # rag / short_term
    message: str             # "帮我分析一下贵州茅台今天的走势"
    cron_expr: str           # "0 15 * * 1-5" (周一到周五15:00)
    create_session: bool = True  # 是否自动创建专属 session
```

**WebSocket 通知消息格式:**

```json
{
  "type": "task_completed",
  "task_id": "xxx",
  "task_name": "每日看茅台",
  "session_id": "xxx",
  "summary": "茅台今天涨了2%..."
}
```

**Step 1~4: 实现路由 + WS + 测试**

Commit: `feat(scheduler): REST API 6 端点 + WebSocket 通知通道`

---

### Task 4: 前端任务管理 UI

**Files:**
- Create: `frontend/types/scheduler.ts`
- Create: `frontend/stores/useSchedulerStore.ts`
- Create: `frontend/app/expert/components/ScheduledTasks.tsx`
- Modify: `frontend/app/expert/page.tsx` (嵌入任务面板)
- Install: `sonner` (toast 通知)

**前端功能:**
1. 任务列表面板（折叠式，在专家页面侧边栏）
2. 创建任务表单（自然语言时间描述 → cron 转换提示）
3. 任务状态卡片（显示名称、cron、上次执行时间、结果摘要）
4. 暂停/恢复/删除/立即执行按钮
5. WebSocket 连接 — 任务完成时弹出 sonner toast
6. 点击任务卡片 → 跳转到对应 session 查看完整分析

**常用 cron 预设:**

| 预设 | cron | 说明 |
|------|------|------|
| 每日收盘后 | `0 15 * * 1-5` | 周一到周五 15:00 |
| 每日开盘前 | `15 9 * * 1-5` | 周一到周五 9:15 |
| 每周一早盘 | `30 9 * * 1` | 周一 9:30 |
| 每月第一个交易日 | `0 15 1 * *` | 每月1号 15:00 |

Commit: `feat(scheduler): 前端任务管理 UI + sonner 通知 + WebSocket`

---

## 用户体验示例

```
用户: "帮我每天收盘后看看贵州茅台和宁德时代"
→ 系统创建定时任务:
  - 名称: 每日收盘分析 — 茅台&宁德时代
  - cron: 0 15 * * 1-5
  - 专家: rag (总顾问，调度4个专家)
  - 自动创建专属 session

→ 每天 15:00 自动执行:
  1. APScheduler 触发 → execute_task()
  2. ExpertAgent.chat("帮我分析一下贵州茅台和宁德时代今天的走势")
  3. 4 个专家分别分析 → 总顾问综合研判
  4. 结果写入 session
  5. WebSocket 推送通知 → 前端弹出 toast: "📊 每日收盘分析完成，点击查看"
  6. 用户点击 toast → 跳转到 session 查看完整分析
```
