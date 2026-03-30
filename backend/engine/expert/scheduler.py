"""定时专家任务调度系统

基于 APScheduler AsyncIOScheduler，嵌入 FastAPI 事件循环。
任务定义持久化到 DuckDB，执行结果写入 Session 体系。

用户可预约 "每天收盘后帮我看茅台" 这类任务，
到时间自动让专家团队执行分析并推送结果。
"""

import uuid
import time
from datetime import datetime
from typing import Any, Callable, Awaitable

import duckdb
from loguru import logger


class ScheduledTaskManager:
    """定时任务管理器 — CRUD + APScheduler 集成 + 任务执行"""

    def __init__(
        self,
        db_path: str,
        agent: Any | None = None,
        engine_experts: dict | None = None,
        on_complete: Callable[[str, str, str], Awaitable[None]] | None = None,
    ):
        self._db_path = db_path
        self._agent = agent
        self._engine_experts = engine_experts or {}
        self._on_complete = on_complete  # callback(task_id, task_name, full_text)
        self._scheduler = None
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
            # Phase 2: 用户隔离
            con.execute("""
                ALTER TABLE expert.scheduled_tasks
                ADD COLUMN IF NOT EXISTS user_id VARCHAR DEFAULT 'anonymous'
            """)
            try:
                con.execute("CREATE INDEX idx_scheduled_tasks_user_id ON expert.scheduled_tasks(user_id)")
            except Exception:
                pass
        finally:
            con.close()

    # ── CRUD ─────────────────────────────────────────────

    def create_task(
        self,
        name: str,
        expert_type: str,
        message: str,
        cron_expr: str,
        persona: str = "rag",
        session_id: str | None = None,
        user_id: str = "anonymous",
    ) -> dict:
        """创建定时任务"""
        task_id = str(uuid.uuid4())
        now = datetime.now()
        con = self._get_db()
        try:
            con.execute(
                """INSERT INTO expert.scheduled_tasks
                   (id, name, expert_type, persona, message, cron_expr, session_id, status, created_at, user_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                [task_id, name, expert_type, persona, message, cron_expr,
                 session_id, "active", now, user_id],
            )
            task = {
                "id": task_id, "name": name, "expert_type": expert_type,
                "persona": persona, "message": message, "cron_expr": cron_expr,
                "session_id": session_id, "status": "active",
                "last_run_at": None, "last_result_summary": None,
                "next_run_at": None, "created_at": now.isoformat(),
                "user_id": user_id,
            }
        finally:
            con.close()

        # 注册到 APScheduler
        if self._scheduler:
            self._register_job(task)

        return task

    def list_tasks(self) -> list[dict]:
        """列出所有定时任务"""
        con = self._get_db()
        try:
            rows = con.execute(
                "SELECT id, name, expert_type, persona, message, cron_expr, session_id, "
                "status, last_run_at, last_result_summary, next_run_at, created_at "
                "FROM expert.scheduled_tasks ORDER BY created_at DESC"
            ).fetchall()
            cols = [
                "id", "name", "expert_type", "persona", "message", "cron_expr",
                "session_id", "status", "last_run_at", "last_result_summary",
                "next_run_at", "created_at",
            ]
            tasks = []
            for r in rows:
                task = dict(zip(cols, r))
                # 序列化 datetime
                for k in ("last_run_at", "next_run_at", "created_at"):
                    if task[k] is not None and not isinstance(task[k], str):
                        task[k] = str(task[k])
                tasks.append(task)
            return tasks
        finally:
            con.close()

    def get_task(self, task_id: str) -> dict | None:
        """获取单个任务详情"""
        con = self._get_db()
        try:
            row = con.execute(
                "SELECT id, name, expert_type, persona, message, cron_expr, session_id, "
                "status, last_run_at, last_result_summary, next_run_at, created_at "
                "FROM expert.scheduled_tasks WHERE id = ?", [task_id]
            ).fetchone()
            if not row:
                return None
            cols = [
                "id", "name", "expert_type", "persona", "message", "cron_expr",
                "session_id", "status", "last_run_at", "last_result_summary",
                "next_run_at", "created_at",
            ]
            task = dict(zip(cols, row))
            for k in ("last_run_at", "next_run_at", "created_at"):
                if task[k] is not None and not isinstance(task[k], str):
                    task[k] = str(task[k])
            return task
        finally:
            con.close()

    def delete_task(self, task_id: str):
        """删除定时任务"""
        self._unregister_job(task_id)
        con = self._get_db()
        try:
            con.execute("DELETE FROM expert.scheduled_tasks WHERE id = ?", [task_id])
        finally:
            con.close()

    def pause_task(self, task_id: str):
        """暂停定时任务"""
        self._unregister_job(task_id)
        con = self._get_db()
        try:
            con.execute(
                "UPDATE expert.scheduled_tasks SET status = 'paused' WHERE id = ?",
                [task_id],
            )
        finally:
            con.close()

    def resume_task(self, task_id: str):
        """恢复定时任务"""
        con = self._get_db()
        try:
            con.execute(
                "UPDATE expert.scheduled_tasks SET status = 'active' WHERE id = ?",
                [task_id],
            )
        finally:
            con.close()
        # 重新注册到 scheduler
        task = self.get_task(task_id)
        if task and self._scheduler:
            self._register_job(task)

    def update_last_run(self, task_id: str, result_summary: str):
        """更新任务的最近执行时间和结果摘要"""
        con = self._get_db()
        try:
            con.execute(
                "UPDATE expert.scheduled_tasks SET last_run_at = ?, last_result_summary = ? WHERE id = ?",
                [datetime.now(), result_summary[:500], task_id],
            )
        finally:
            con.close()

    # ── APScheduler 集成 ─────────────────────────────────

    def start_scheduler(self):
        """启动 APScheduler 并从 DB 恢复所有 active 任务"""
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
        except ImportError:
            logger.error("❌ apscheduler 未安装，定时任务功能不可用！请运行: pip install apscheduler>=3.10.0")
            return

        self._scheduler = AsyncIOScheduler()
        self._scheduler.start()
        logger.info("⏰ APScheduler 已启动")

        # 从 DB 恢复已有任务
        restored = 0
        for task in self.list_tasks():
            if task["status"] == "active":
                self._register_job(task)
                restored += 1
        if restored:
            logger.info(f"⏰ 已恢复 {restored} 个定时任务")

    def _register_job(self, task: dict):
        """将任务注册到 APScheduler"""
        if not self._scheduler:
            return
        try:
            from apscheduler.triggers.cron import CronTrigger

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
        if not self._scheduler:
            return
        try:
            if self._scheduler.get_job(task_id):
                self._scheduler.remove_job(task_id)
        except Exception:
            pass

    async def _job_wrapper(self, task_id: str):
        """APScheduler 定时触发的 wrapper"""
        task = self.get_task(task_id)
        name = task["name"] if task else task_id
        logger.info(f"⏰ 定时任务开始执行: {name} ({task_id})")
        try:
            result = await self.execute_task(task_id)
            logger.info(f"⏰ 定时任务完成: {name}, 结果长度: {len(result)}")
        except Exception as e:
            logger.error(f"⏰ 定时任务失败: {name}: {e}")

    # ── 任务执行 ─────────────────────────────────────────

    async def execute_task(self, task_id: str) -> str:
        """执行一次任务 — 调用专家 chat() 收集完整回复

        可被 APScheduler 定时触发，也可被 REST API 手动触发。
        """
        start = time.time()

        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")

        expert_type = task["expert_type"]
        persona = task.get("persona", "rag")
        message = task["message"]
        session_id = task.get("session_id")

        # 调用专家
        full_text = ""
        try:
            if expert_type in ("rag", "short_term"):
                if not self._agent:
                    return "Agent 未初始化，无法执行"
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
        except Exception as e:
            logger.error(f"任务执行异常 [{task_id}]: {e}")
            full_text = f"执行异常: {e}"

        elapsed = time.time() - start
        logger.info(f"⏰ 任务 {task['name']} 执行耗时: {elapsed:.1f}s")

        # 写入 Session 消息体系
        if session_id:
            self._save_to_session(session_id, message, full_text)

        # 更新任务状态
        summary = full_text[:500] if full_text else "无结果"
        self.update_last_run(task_id, summary)

        # 通知回调
        if self._on_complete:
            try:
                await self._on_complete(task_id, task["name"], full_text)
            except Exception as e:
                logger.warning(f"通知回调失败: {e}")

        return full_text

    def _save_to_session(self, session_id: str, user_msg: str, expert_reply: str):
        """将执行结果存入 Session 消息体系"""
        con = self._get_db()
        try:
            now = datetime.now()
            # 用户消息（标记为定时任务）
            con.execute(
                "INSERT INTO expert.messages (id, session_id, role, content, created_at) VALUES (?,?,?,?,?)",
                [str(uuid.uuid4()), session_id, "user", f"[⏰ 定时任务] {user_msg}", now],
            )
            # 专家回复
            con.execute(
                "INSERT INTO expert.messages (id, session_id, role, content, created_at) VALUES (?,?,?,?,?)",
                [str(uuid.uuid4()), session_id, "expert", expert_reply, now],
            )
            # 更新 session 时间戳
            con.execute(
                "UPDATE expert.sessions SET updated_at = ? WHERE id = ?",
                [now, session_id],
            )
        except Exception as e:
            logger.warning(f"保存到 Session 失败: {e}")
        finally:
            con.close()

    def shutdown(self):
        """关闭调度器"""
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            logger.info("⏰ APScheduler 已关闭")
