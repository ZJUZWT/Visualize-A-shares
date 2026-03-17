"""定时专家任务系统测试"""

import pytest
from unittest.mock import MagicMock

from engine.expert.scheduler import ScheduledTaskManager


@pytest.fixture
def manager(tmp_path):
    db_path = str(tmp_path / "test.duckdb")
    return ScheduledTaskManager(db_path, agent=None, engine_experts={})


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
        assert task["expert_type"] == "rag"
        assert task["cron_expr"] == "0 15 * * 1-5"

    def test_list_tasks(self, manager):
        manager.create_task(name="任务1", expert_type="rag", message="msg1", cron_expr="0 15 * * 1-5")
        manager.create_task(name="任务2", expert_type="short_term", message="msg2", cron_expr="0 9 * * 1-5")
        tasks = manager.list_tasks()
        assert len(tasks) == 2

    def test_get_task(self, manager):
        task = manager.create_task(name="测试", expert_type="rag", message="msg", cron_expr="0 15 * * 1-5")
        fetched = manager.get_task(task["id"])
        assert fetched is not None
        assert fetched["name"] == "测试"

    def test_get_task_not_found(self, manager):
        assert manager.get_task("nonexistent") is None

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
        manager.update_last_run(task["id"], "茅台今天涨了2%，技术面看好")
        tasks = manager.list_tasks()
        assert tasks[0]["last_run_at"] is not None
        assert "茅台" in tasks[0]["last_result_summary"]

    def test_create_with_session_id(self, manager):
        task = manager.create_task(
            name="带session", expert_type="rag", message="msg",
            cron_expr="0 15 * * 1-5", session_id="test-session-123",
        )
        assert task["session_id"] == "test-session-123"

    def test_create_with_persona(self, manager):
        task = manager.create_task(
            name="短线", expert_type="rag", message="msg",
            cron_expr="0 15 * * 1-5", persona="short_term",
        )
        assert task["persona"] == "short_term"


class TestTaskExecution:
    @pytest.mark.asyncio
    async def test_execute_task_rag(self, tmp_path):
        """RAG 专家任务执行，收集完整回复"""
        db_path = str(tmp_path / "test.duckdb")

        mock_agent = MagicMock()
        async def fake_chat(message, history=None, persona="rag"):
            yield {"event": "thinking_start", "data": {}}
            yield {"event": "reply_token", "data": {"token": "茅台"}}
            yield {"event": "reply_token", "data": {"token": "今天涨了"}}
            yield {"event": "reply_complete", "data": {"full_text": "茅台今天涨了2%，技术面看好"}}
        mock_agent.chat = fake_chat

        manager = ScheduledTaskManager(db_path, agent=mock_agent, engine_experts={})
        task = manager.create_task(
            name="测试RAG", expert_type="rag",
            message="分析茅台", cron_expr="0 15 * * 1-5",
        )

        result = await manager.execute_task(task["id"])
        assert "茅台" in result
        assert "涨了" in result

        # 验证 last_run 已更新
        updated = manager.get_task(task["id"])
        assert updated["last_run_at"] is not None
        assert "茅台" in updated["last_result_summary"]

    @pytest.mark.asyncio
    async def test_execute_task_engine_expert(self, tmp_path):
        """引擎专家任务执行"""
        db_path = str(tmp_path / "test.duckdb")

        mock_expert = MagicMock()
        async def fake_chat(message, history=None):
            yield {"event": "reply_complete", "data": {"full_text": "MACD金叉信号，RSI 45"}}
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

    @pytest.mark.asyncio
    async def test_execute_task_not_found(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        manager = ScheduledTaskManager(db_path)
        with pytest.raises(ValueError, match="任务不存在"):
            await manager.execute_task("nonexistent")

    @pytest.mark.asyncio
    async def test_execute_task_no_agent(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        manager = ScheduledTaskManager(db_path, agent=None)
        task = manager.create_task(name="无agent", expert_type="rag", message="msg", cron_expr="0 15 * * 1-5")
        result = await manager.execute_task(task["id"])
        assert "未初始化" in result

    @pytest.mark.asyncio
    async def test_execute_with_on_complete_callback(self, tmp_path):
        """验证完成回调被调用"""
        db_path = str(tmp_path / "test.duckdb")
        callback_called = {}

        async def on_complete(task_id, task_name, full_text):
            callback_called["task_id"] = task_id
            callback_called["text"] = full_text

        mock_agent = MagicMock()
        async def fake_chat(message, history=None, persona="rag"):
            yield {"event": "reply_complete", "data": {"full_text": "回调测试结果"}}
        mock_agent.chat = fake_chat

        manager = ScheduledTaskManager(
            db_path, agent=mock_agent, on_complete=on_complete,
        )
        task = manager.create_task(name="回调测试", expert_type="rag", message="msg", cron_expr="0 15 * * 1-5")
        await manager.execute_task(task["id"])

        assert callback_called["task_id"] == task["id"]
        assert "回调测试" in callback_called["text"]

    @pytest.mark.asyncio
    async def test_execute_saves_to_session(self, tmp_path):
        """验证执行结果写入 Session"""
        db_path = str(tmp_path / "test.duckdb")
        import duckdb
        # 预建 session
        con = duckdb.connect(db_path)
        con.execute("CREATE SCHEMA IF NOT EXISTS expert")
        con.execute("""CREATE TABLE IF NOT EXISTS expert.sessions (
            id VARCHAR PRIMARY KEY, expert_type VARCHAR, title VARCHAR,
            created_at TIMESTAMP, updated_at TIMESTAMP
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS expert.messages (
            id VARCHAR PRIMARY KEY, session_id VARCHAR, role VARCHAR,
            content VARCHAR, thinking JSON, created_at TIMESTAMP
        )""")
        con.execute("INSERT INTO expert.sessions VALUES ('s1','rag','测试',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
        con.close()

        mock_agent = MagicMock()
        async def fake_chat(message, history=None, persona="rag"):
            yield {"event": "reply_complete", "data": {"full_text": "分析结果xxx"}}
        mock_agent.chat = fake_chat

        manager = ScheduledTaskManager(db_path, agent=mock_agent)
        task = manager.create_task(
            name="写session", expert_type="rag", message="分析一下",
            cron_expr="0 15 * * 1-5", session_id="s1",
        )
        await manager.execute_task(task["id"])

        # 验证消息已写入
        con = duckdb.connect(db_path)
        msgs = con.execute("SELECT role, content FROM expert.messages WHERE session_id = 's1' ORDER BY created_at").fetchall()
        con.close()
        assert len(msgs) == 2
        assert msgs[0][0] == "user"
        assert "⏰ 定时任务" in msgs[0][1]
        assert msgs[1][0] == "expert"
        assert "分析结果" in msgs[1][1]
