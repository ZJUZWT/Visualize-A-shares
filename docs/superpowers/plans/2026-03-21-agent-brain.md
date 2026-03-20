# Agent Brain Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 Main Agent 一个大脑，让它能全自主地分析市场、做出交易决策、在虚拟持仓上执行，用户可以查看完整思考过程。

**Architecture:** 后端新增 watchlist/brain_runs/brain_config 三张表，brain.py 核心决策模块调用现有专家工具层获取数据、LLM 综合决策、自动执行交易。APScheduler 定时触发。前端新增 /agent 页面展示运行记录和思考过程。

**Tech Stack:** Python/FastAPI/DuckDB/APScheduler (后端), Next.js/React/TypeScript (前端)

**Spec:** `docs/superpowers/specs/2026-03-21-agent-brain-design.md`

---

## File Structure

```
backend/
├── engine/agent/
│   ├── db.py                          ← 修改: _init_tables 新增 3 张表
│   ├── models.py                      ← 修改: 新增 Watchlist/BrainRun/BrainConfig 模型
│   ├── service.py                     ← 修改: 新增 watchlist + brain_runs CRUD
│   ├── routes.py                      ← 修改: 新增 watchlist + brain API 端点
│   ├── brain.py                       ← 新建: Agent Brain 核心决策逻辑
│   └── scheduler.py                   ← 新建: Agent 定时调度

tests/unit/
└── test_agent_brain.py                ← 新建: Agent Brain 测试

frontend/
├── components/ui/
│   └── NavSidebar.tsx                 ← 修改: 新增 /agent 导航项
├── app/agent/
│   └── page.tsx                       ← 新建: Agent 页面
```

---

## Chunk 1: 后端数据层 (Task 1-3)

### Task 1: 新增 3 张表 + 数据模型

**Files:**
- Modify: `backend/engine/agent/db.py`
- Modify: `backend/engine/agent/models.py`
- Create: `tests/unit/test_agent_brain.py`

- [ ] **Step 1: 写表和模型的失败测试**

创建 `tests/unit/test_agent_brain.py`：

```python
"""Agent Brain 单元测试"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

import asyncio
import tempfile
import duckdb
import pytest
from unittest.mock import patch

def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ═══════════════════════════════════════════════════════
# Task 1: 表 + 模型
# ═══════════════════════════════════════════════════════

class TestBrainTables:
    """新增表测试"""

    def test_tables_exist(self, tmp_path):
        db_path = tmp_path / "test_agent.duckdb"
        with patch("engine.agent.db.AGENT_DB_PATH", db_path):
            from engine.agent.db import AgentDB
            AgentDB._instance = None
            db = AgentDB.init_instance()

        conn = duckdb.connect(str(db_path))
        tables = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='agent'"
        ).fetchall()
        table_names = {t[0] for t in tables}
        conn.close()
        db.close()

        assert "watchlist" in table_names
        assert "brain_runs" in table_names
        assert "brain_config" in table_names


class TestBrainModels:
    """Pydantic 模型测试"""

    def test_watchlist_input(self):
        from engine.agent.models import WatchlistInput
        w = WatchlistInput(stock_code="600519", stock_name="贵州茅台", reason="白酒龙头")
        assert w.stock_code == "600519"

    def test_brain_config_defaults(self):
        from engine.agent.models import BrainConfig
        c = BrainConfig()
        assert c.enable_debate is False
        assert c.max_candidates == 30
        assert c.quant_top_n == 20
        assert c.max_position_count == 10
        assert c.single_position_pct == 0.15
        assert c.schedule_time == "15:30"

    def test_brain_run_model(self):
        from engine.agent.models import BrainRun
        r = BrainRun(
            id="test", portfolio_id="p1",
            started_at="2026-03-21T15:30:00",
        )
        assert r.status == "running"
        assert r.candidates is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/test_agent_brain.py -v`
Expected: FAIL — tables/models not found

- [ ] **Step 3: 在 db.py _init_tables 中新增 3 张表**

在 `backend/engine/agent/db.py` 的 `_init_tables` 方法末尾（trade_plans 表之后）追加：

```python
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS agent.watchlist (
                id VARCHAR PRIMARY KEY,
                stock_code VARCHAR NOT NULL,
                stock_name VARCHAR NOT NULL,
                reason TEXT,
                added_by VARCHAR DEFAULT 'manual',
                created_at TIMESTAMP DEFAULT now()
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS agent.brain_runs (
                id VARCHAR PRIMARY KEY,
                portfolio_id VARCHAR NOT NULL,
                run_type VARCHAR DEFAULT 'scheduled',
                status VARCHAR DEFAULT 'running',
                candidates JSON,
                analysis_results JSON,
                decisions JSON,
                plan_ids JSON,
                trade_ids JSON,
                error_message TEXT,
                llm_tokens_used INTEGER DEFAULT 0,
                started_at TIMESTAMP DEFAULT now(),
                completed_at TIMESTAMP
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS agent.brain_config (
                id VARCHAR PRIMARY KEY DEFAULT 'default',
                enable_debate BOOLEAN DEFAULT false,
                max_candidates INTEGER DEFAULT 30,
                quant_top_n INTEGER DEFAULT 20,
                max_position_count INTEGER DEFAULT 10,
                single_position_pct DOUBLE DEFAULT 0.15,
                schedule_time VARCHAR DEFAULT '15:30',
                updated_at TIMESTAMP DEFAULT now()
            )
        """)
        # 插入默认配置（幂等）
        self._conn.execute("""
            INSERT INTO agent.brain_config (id) VALUES ('default')
            ON CONFLICT (id) DO NOTHING
        """)
```

- [ ] **Step 4: 在 models.py 中新增模型**

在 `backend/engine/agent/models.py` 末尾追加：

```python
# ── 关注列表 ──────────────────────────────────────────

class WatchlistItem(BaseModel):
    id: str
    stock_code: str
    stock_name: str
    reason: str | None = None
    added_by: Literal["manual", "agent"] = "manual"
    created_at: str


class WatchlistInput(BaseModel):
    stock_code: str
    stock_name: str
    reason: str | None = None


# ── Agent Brain ───────────────────────────────────────

class BrainRun(BaseModel):
    id: str
    portfolio_id: str
    run_type: Literal["scheduled", "manual"] = "scheduled"
    status: Literal["running", "completed", "failed"] = "running"
    candidates: list[dict] | None = None
    analysis_results: list[dict] | None = None
    decisions: list[dict] | None = None
    plan_ids: list[str] | None = None
    trade_ids: list[str] | None = None
    error_message: str | None = None
    llm_tokens_used: int = 0
    started_at: str
    completed_at: str | None = None


class BrainConfig(BaseModel):
    enable_debate: bool = False
    max_candidates: int = 30
    quant_top_n: int = 20
    max_position_count: int = 10
    single_position_pct: float = 0.15
    schedule_time: str = "15:30"
```

- [ ] **Step 5: 更新 test_agent_phase1a.py 的表断言**

在 `tests/unit/test_agent_phase1a.py` 中更新 expected 表集合，加入 `"watchlist"`, `"brain_runs"`, `"brain_config"`。

- [ ] **Step 6: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/test_agent_brain.py tests/unit/test_agent_phase1a.py::TestAgentDB -v`
Expected: 全部通过

- [ ] **Step 7: Commit**

```bash
git add backend/engine/agent/db.py backend/engine/agent/models.py tests/unit/test_agent_brain.py tests/unit/test_agent_phase1a.py
git commit -m "feat(brain): watchlist + brain_runs + brain_config 表 + 模型"
```

---

### Task 2: Service 层 — Watchlist + BrainRuns CRUD

**Files:**
- Modify: `backend/engine/agent/service.py`
- Test: `tests/unit/test_agent_brain.py` (追加)

- [ ] **Step 1: 写 CRUD 失败测试**

在 `tests/unit/test_agent_brain.py` 末尾追加：

```python
# ═══════════════════════════════════════════════════════
# Task 2: Watchlist + BrainRuns CRUD
# ═══════════════════════════════════════════════════════

def _make_service(tmp_dir):
    db_path = Path(tmp_dir) / "test_agent.duckdb"
    with patch("engine.agent.db.AGENT_DB_PATH", db_path):
        from engine.agent.db import AgentDB
        AgentDB._instance = None
        db = AgentDB.init_instance()
    from engine.agent.validator import TradeValidator
    from engine.agent.service import AgentService
    svc = AgentService(db=db, validator=TradeValidator())
    return db, svc


class TestServiceWatchlist:
    """Watchlist CRUD 测试"""

    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, self.svc = _make_service(self._tmp)

    def teardown_method(self):
        self.db.close()

    def test_add_watchlist(self):
        from engine.agent.models import WatchlistInput
        result = run(self.svc.add_watchlist(WatchlistInput(
            stock_code="600519", stock_name="贵州茅台", reason="白酒龙头"
        )))
        assert result["stock_code"] == "600519"
        assert result["added_by"] == "manual"

    def test_list_watchlist(self):
        from engine.agent.models import WatchlistInput
        run(self.svc.add_watchlist(WatchlistInput(stock_code="600519", stock_name="贵州茅台")))
        run(self.svc.add_watchlist(WatchlistInput(stock_code="601318", stock_name="中国平安")))
        result = run(self.svc.list_watchlist())
        assert len(result) == 2

    def test_remove_watchlist(self):
        from engine.agent.models import WatchlistInput
        item = run(self.svc.add_watchlist(WatchlistInput(stock_code="600519", stock_name="贵州茅台")))
        run(self.svc.remove_watchlist(item["id"]))
        result = run(self.svc.list_watchlist())
        assert len(result) == 0

    def test_remove_watchlist_not_found(self):
        with pytest.raises(ValueError, match="不存在"):
            run(self.svc.remove_watchlist("nonexistent"))

    def test_add_duplicate_watchlist(self):
        from engine.agent.models import WatchlistInput
        run(self.svc.add_watchlist(WatchlistInput(stock_code="600519", stock_name="贵州茅台")))
        run(self.svc.add_watchlist(WatchlistInput(stock_code="600519", stock_name="贵州茅台")))
        result = run(self.svc.list_watchlist())
        # 允许重复添加，不报错
        assert len(result) == 2


class TestServiceBrainRuns:
    """BrainRuns CRUD 测试"""

    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, self.svc = _make_service(self._tmp)

    def teardown_method(self):
        self.db.close()

    def test_create_brain_run(self):
        result = run(self.svc.create_brain_run("portfolio_1", "manual"))
        assert result["status"] == "running"
        assert result["portfolio_id"] == "portfolio_1"
        assert result["run_type"] == "manual"

    def test_update_brain_run(self):
        created = run(self.svc.create_brain_run("portfolio_1"))
        run(self.svc.update_brain_run(created["id"], {
            "status": "completed",
            "decisions": [{"action": "buy", "stock_code": "600519"}],
        }))
        result = run(self.svc.get_brain_run(created["id"]))
        assert result["status"] == "completed"

    def test_list_brain_runs(self):
        run(self.svc.create_brain_run("portfolio_1"))
        run(self.svc.create_brain_run("portfolio_1"))
        result = run(self.svc.list_brain_runs("portfolio_1"))
        assert len(result) == 2

    def test_get_brain_run_not_found(self):
        with pytest.raises(ValueError, match="不存在"):
            run(self.svc.get_brain_run("nonexistent"))

    def test_get_brain_config(self):
        result = run(self.svc.get_brain_config())
        assert result["enable_debate"] is False
        assert result["max_candidates"] == 30

    def test_update_brain_config(self):
        run(self.svc.update_brain_config({"enable_debate": True, "max_candidates": 50}))
        result = run(self.svc.get_brain_config())
        assert result["enable_debate"] is True
        assert result["max_candidates"] == 50
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/test_agent_brain.py::TestServiceWatchlist -v`
Expected: FAIL — `AttributeError: 'AgentService' object has no attribute 'add_watchlist'`

- [ ] **Step 3: 在 service.py 中追加 Watchlist + BrainRuns CRUD**

在 `AgentService` 类末尾追加：

```python
    # ── Watchlist CRUD ─────────────────────────────────

    async def add_watchlist(self, item_input) -> dict:
        """添加关注"""
        item_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        await self.db.execute_write(
            """INSERT INTO agent.watchlist (id, stock_code, stock_name, reason, added_by, created_at)
               VALUES (?, ?, ?, ?, 'manual', ?)""",
            [item_id, item_input.stock_code, item_input.stock_name,
             item_input.reason, now],
        )
        rows = await self.db.execute_read(
            "SELECT * FROM agent.watchlist WHERE id = ?", [item_id]
        )
        return rows[0]

    async def list_watchlist(self) -> list[dict]:
        """关注列表"""
        return await self.db.execute_read(
            "SELECT * FROM agent.watchlist ORDER BY created_at DESC"
        )

    async def remove_watchlist(self, item_id: str):
        """取消关注"""
        rows = await self.db.execute_read(
            "SELECT id FROM agent.watchlist WHERE id = ?", [item_id]
        )
        if not rows:
            raise ValueError(f"关注项 {item_id} 不存在")
        await self.db.execute_write(
            "DELETE FROM agent.watchlist WHERE id = ?", [item_id]
        )

    # ── BrainRuns CRUD ─────────────────────────────────

    async def create_brain_run(self, portfolio_id: str, run_type: str = "scheduled") -> dict:
        """创建运行记录"""
        run_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        await self.db.execute_write(
            """INSERT INTO agent.brain_runs (id, portfolio_id, run_type, status, started_at)
               VALUES (?, ?, ?, 'running', ?)""",
            [run_id, portfolio_id, run_type, now],
        )
        rows = await self.db.execute_read(
            "SELECT * FROM agent.brain_runs WHERE id = ?", [run_id]
        )
        return rows[0]

    async def get_brain_run(self, run_id: str) -> dict:
        """获取运行记录"""
        rows = await self.db.execute_read(
            "SELECT * FROM agent.brain_runs WHERE id = ?", [run_id]
        )
        if not rows:
            raise ValueError(f"运行记录 {run_id} 不存在")
        return rows[0]

    async def update_brain_run(self, run_id: str, updates: dict):
        """更新运行记录"""
        await self.get_brain_run(run_id)
        sets = []
        params = []
        for key in ("status", "candidates", "analysis_results", "decisions",
                     "plan_ids", "trade_ids", "error_message", "llm_tokens_used"):
            if key in updates:
                val = updates[key]
                if isinstance(val, (list, dict)):
                    import json as _json
                    val = _json.dumps(val, ensure_ascii=False)
                sets.append(f"{key} = ?")
                params.append(val)
        if "status" in updates and updates["status"] in ("completed", "failed"):
            sets.append("completed_at = ?")
            params.append(datetime.now().isoformat())
        if sets:
            sql = f"UPDATE agent.brain_runs SET {', '.join(sets)} WHERE id = ?"
            params.append(run_id)
            await self.db.execute_write(sql, params)

    async def list_brain_runs(self, portfolio_id: str, limit: int = 50) -> list[dict]:
        """运行记录列表"""
        return await self.db.execute_read(
            "SELECT * FROM agent.brain_runs WHERE portfolio_id = ? ORDER BY started_at DESC LIMIT ?",
            [portfolio_id, limit],
        )

    # ── BrainConfig CRUD ───────────────────────────────

    async def get_brain_config(self) -> dict:
        """获取 Brain 配置"""
        rows = await self.db.execute_read(
            "SELECT * FROM agent.brain_config WHERE id = 'default'"
        )
        if not rows:
            return {"enable_debate": False, "max_candidates": 30, "quant_top_n": 20,
                    "max_position_count": 10, "single_position_pct": 0.15, "schedule_time": "15:30"}
        return rows[0]

    async def update_brain_config(self, updates: dict):
        """更新 Brain 配置"""
        sets = []
        params = []
        for key in ("enable_debate", "max_candidates", "quant_top_n",
                     "max_position_count", "single_position_pct", "schedule_time"):
            if key in updates:
                sets.append(f"{key} = ?")
                params.append(updates[key])
        if sets:
            sets.append("updated_at = ?")
            params.append(datetime.now().isoformat())
            sql = f"UPDATE agent.brain_config SET {', '.join(sets)} WHERE id = 'default'"
            await self.db.execute_write(sql, params)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/test_agent_brain.py -v`
Expected: 全部通过

- [ ] **Step 5: Commit**

```bash
git add backend/engine/agent/service.py tests/unit/test_agent_brain.py
git commit -m "feat(brain): Watchlist + BrainRuns + BrainConfig CRUD"
```

---

### Task 3: FastAPI 路由 — Watchlist + Brain API

**Files:**
- Modify: `backend/engine/agent/routes.py`
- Test: `tests/unit/test_agent_brain.py` (追加)

- [ ] **Step 1: 写路由失败测试**

在 `tests/unit/test_agent_brain.py` 末尾追加：

```python
# ═══════════════════════════════════════════════════════
# Task 3: FastAPI Routes
# ═══════════════════════════════════════════════════════
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _create_test_app(tmp_dir):
    db_path = Path(tmp_dir) / "test_agent.duckdb"
    with patch("engine.agent.db.AGENT_DB_PATH", db_path):
        from engine.agent.db import AgentDB
        AgentDB._instance = None
        db = AgentDB.init_instance()
    from engine.agent.routes import create_agent_router
    app = FastAPI()
    app.include_router(create_agent_router(), prefix="/api/v1/agent")
    return app, db


class TestWatchlistRoutes:
    """Watchlist API 路由测试"""

    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.app, self.db = _create_test_app(self._tmp)
        self.client = TestClient(self.app)

    def teardown_method(self):
        self.db.close()

    def test_add_watchlist(self):
        resp = self.client.post("/api/v1/agent/watchlist", json={
            "stock_code": "600519", "stock_name": "贵州茅台", "reason": "白酒龙头"
        })
        assert resp.status_code == 200
        assert resp.json()["stock_code"] == "600519"

    def test_list_watchlist(self):
        self.client.post("/api/v1/agent/watchlist", json={"stock_code": "600519", "stock_name": "贵州茅台"})
        resp = self.client.get("/api/v1/agent/watchlist")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_delete_watchlist(self):
        r = self.client.post("/api/v1/agent/watchlist", json={"stock_code": "600519", "stock_name": "贵州茅台"})
        item_id = r.json()["id"]
        resp = self.client.delete(f"/api/v1/agent/watchlist/{item_id}")
        assert resp.status_code == 200
        resp = self.client.get("/api/v1/agent/watchlist")
        assert len(resp.json()) == 0

    def test_delete_watchlist_404(self):
        resp = self.client.delete("/api/v1/agent/watchlist/nonexistent")
        assert resp.status_code == 404


class TestBrainRoutes:
    """Brain API 路由测试"""

    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.app, self.db = _create_test_app(self._tmp)
        self.client = TestClient(self.app)

    def teardown_method(self):
        self.db.close()

    def test_get_brain_config(self):
        resp = self.client.get("/api/v1/agent/brain/config")
        assert resp.status_code == 200
        assert resp.json()["enable_debate"] is False

    def test_update_brain_config(self):
        resp = self.client.patch("/api/v1/agent/brain/config", json={"enable_debate": True})
        assert resp.status_code == 200
        resp = self.client.get("/api/v1/agent/brain/config")
        assert resp.json()["enable_debate"] is True

    def test_list_brain_runs_empty(self):
        # 需要先创建 portfolio
        self.client.post("/api/v1/agent/portfolio", json={
            "id": "p1", "mode": "live", "initial_capital": 1000000
        })
        resp = self.client.get("/api/v1/agent/brain/runs?portfolio_id=p1")
        assert resp.status_code == 200
        assert len(resp.json()) == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/test_agent_brain.py::TestWatchlistRoutes -v`
Expected: FAIL — 路由不存在

- [ ] **Step 3: 在 routes.py 中新增端点**

在 `backend/engine/agent/routes.py` 中：

1. 顶部 import 新增：
```python
from engine.agent.models import TradeInput, TradePlanInput, TradePlanUpdate, WatchlistInput
```

2. 在 `create_agent_router()` 函数内，`return router` 之前追加：

```python
    # ── Watchlist ──

    @router.post("/watchlist")
    async def add_watchlist(req: WatchlistInput):
        svc = _get_service()
        return await svc.add_watchlist(req)

    @router.get("/watchlist")
    async def list_watchlist():
        svc = _get_service()
        return await svc.list_watchlist()

    @router.delete("/watchlist/{item_id}")
    async def remove_watchlist(item_id: str):
        svc = _get_service()
        try:
            await svc.remove_watchlist(item_id)
            return {"ok": True}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    # ── Brain ──

    @router.get("/brain/config")
    async def get_brain_config():
        svc = _get_service()
        return await svc.get_brain_config()

    @router.patch("/brain/config")
    async def update_brain_config(req: dict):
        svc = _get_service()
        await svc.update_brain_config(req)
        return await svc.get_brain_config()

    @router.get("/brain/runs")
    async def list_brain_runs(portfolio_id: str):
        svc = _get_service()
        return await svc.list_brain_runs(portfolio_id)

    @router.get("/brain/runs/{run_id}")
    async def get_brain_run(run_id: str):
        svc = _get_service()
        try:
            return await svc.get_brain_run(run_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.post("/brain/run")
    async def trigger_brain_run(portfolio_id: str):
        """手动触发一次 Brain 运行"""
        svc = _get_service()
        # 创建运行记录，实际执行由 brain.py 处理
        run_record = await svc.create_brain_run(portfolio_id, "manual")
        # 异步启动 brain（不阻塞请求）
        import asyncio
        from engine.agent.brain import AgentBrain
        brain = AgentBrain(portfolio_id)
        asyncio.create_task(brain.execute(run_record["id"]))
        return run_record
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/test_agent_brain.py -v`
Expected: 全部通过（brain/run 端点的测试需要 brain.py 存在，先创建空文件）

- [ ] **Step 5: 创建 brain.py 空壳**

创建 `backend/engine/agent/brain.py`：

```python
"""
AgentBrain — Main Agent 决策大脑
"""
from __future__ import annotations

from loguru import logger


class AgentBrain:
    """Agent 决策大脑"""

    def __init__(self, portfolio_id: str):
        self.portfolio_id = portfolio_id

    async def execute(self, run_id: str):
        """执行一次完整的分析→决策→执行流程"""
        logger.info(f"AgentBrain 运行开始: run_id={run_id}")
        # TODO: Task 4-6 实现
        pass
```

- [ ] **Step 6: 运行全部测试**

Run: `python3 -m pytest tests/unit/test_agent_brain.py tests/unit/test_trade_plans.py tests/unit/test_agent_phase1a.py -v`
Expected: 全部通过

- [ ] **Step 7: Commit**

```bash
git add backend/engine/agent/routes.py backend/engine/agent/brain.py tests/unit/test_agent_brain.py
git commit -m "feat(brain): Watchlist + Brain API 端点 + brain.py 空壳"
```

## Chunk 2: Agent Brain 核心逻辑 (Task 4-6)

### Task 4: brain.py — 标的筛选 + 数据分析

**Files:**
- Modify: `backend/engine/agent/brain.py`
- Test: `tests/unit/test_agent_brain.py` (追加)

- [ ] **Step 1: 写标的筛选的测试**

在 `tests/unit/test_agent_brain.py` 末尾追加：

```python
# ═══════════════════════════════════════════════════════
# Task 4: Brain — 标的筛选 + 数据分析
# ═══════════════════════════════════════════════════════
from unittest.mock import AsyncMock, MagicMock


class TestBrainCandidates:
    """标的筛选测试"""

    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, self.svc = _make_service(self._tmp)

    def teardown_method(self):
        self.db.close()

    def test_merge_candidates(self):
        from engine.agent.brain import AgentBrain
        brain = AgentBrain.__new__(AgentBrain)
        watchlist = [
            {"stock_code": "600519", "stock_name": "贵州茅台"},
            {"stock_code": "601318", "stock_name": "中国平安"},
        ]
        quant_top = [
            {"stock_code": "600519", "score": 0.85},
            {"stock_code": "000858", "score": 0.80},
        ]
        positions = [
            {"stock_code": "601888", "stock_name": "中国中免"},
        ]
        result = brain._merge_candidates(watchlist, quant_top, positions, max_n=30)
        codes = [c["stock_code"] for c in result]
        assert "600519" in codes
        assert "601318" in codes
        assert "000858" in codes
        assert "601888" in codes
        # 600519 不重复
        assert codes.count("600519") == 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/test_agent_brain.py::TestBrainCandidates -v`
Expected: FAIL

- [ ] **Step 3: 实现 brain.py 核心逻辑**

替换 `backend/engine/agent/brain.py` 全文：

```python
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
            config = await self.service.get_brain_config()

            # Step 1: 标的筛选
            candidates = await self._select_candidates(config)
            await self.service.update_brain_run(run_id, {
                "candidates": candidates,
            })
            logger.info(f"🧠 候选标的: {len(candidates)} 只")

            if not candidates:
                await self.service.update_brain_run(run_id, {
                    "status": "completed",
                    "decisions": [],
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
            decisions = await self._make_decisions(analysis_results, portfolio, config)
            await self.service.update_brain_run(run_id, {
                "decisions": decisions,
            })
            logger.info(f"🧠 决策完成: {len(decisions)} 个操作")

            # Step 4: 自动执行
            plan_ids, trade_ids = await self._execute_decisions(decisions)
            elapsed = time.monotonic() - start
            await self.service.update_brain_run(run_id, {
                "status": "completed",
                "plan_ids": plan_ids,
                "trade_ids": trade_ids,
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
        # 关注列表
        watchlist = await self.service.list_watchlist()

        # 量化筛选
        quant_top = await self._quant_screen(config.get("quant_top_n", 20))

        # 已有持仓
        positions = await self.service.get_positions(self.portfolio_id, "open")

        # 合并去重
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

        # 已有持仓优先（必须分析）
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

            # 按预测概率排序取 top N
            sorted_preds = sorted(
                result.predictions.items(),
                key=lambda x: x[1],
                reverse=True,
            )[:top_n]

            return [
                {"stock_code": code, "score": round(score, 4),
                 "stock_name": code}
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

        # 行情数据
        try:
            analysis["daily"] = await tools.execute("data", "get_daily_history", {"code": code, "days": 30})
        except Exception as e:
            analysis["daily"] = f"获取失败: {e}"

        # 技术指标
        try:
            analysis["indicators"] = await tools.execute("quant", "get_technical_indicators", {"code": code})
        except Exception as e:
            analysis["indicators"] = f"获取失败: {e}"

        return analysis

    # ── Step 3: LLM 综合决策 ──────────────────────────

    async def _make_decisions(
        self, analysis_results: list[dict], portfolio: dict, config: dict
    ) -> list[dict]:
        """LLM 综合决策"""
        from llm import LLMProviderFactory, llm_settings
        from llm.providers import ChatMessage

        llm = LLMProviderFactory.create(llm_settings)

        positions_desc = ""
        for p in portfolio.get("positions", []):
            positions_desc += f"  - {p['stock_code']} {p['stock_name']}: {p['current_qty']}股, 成本{p['entry_price']}, 类型{p['holding_type']}\n"
        if not positions_desc:
            positions_desc = "  （空仓）\n"

        analysis_desc = ""
        for a in analysis_results:
            analysis_desc += f"\n### {a['stock_code']} {a.get('stock_name', '')}\n"
            analysis_desc += f"来源: {a.get('source', 'unknown')}\n"
            if "daily" in a and not isinstance(a["daily"], str):
                analysis_desc += f"行情: {a['daily'][:500] if isinstance(a['daily'], str) else str(a['daily'])[:500]}\n"
            if "indicators" in a and not isinstance(a["indicators"], str):
                analysis_desc += f"技术指标: {str(a['indicators'])[:500]}\n"
            if "error" in a:
                analysis_desc += f"分析失败: {a['error']}\n"

        prompt = f"""你是一个专业的 A 股投资 Agent，基于以下分析数据做出交易决策。

## 当前账户状态
- 现金余额：{portfolio['cash_balance']:.2f}
- 总资产：{portfolio['total_asset']:.2f}
- 当前持仓：
{positions_desc}

## 候选标的分析
{analysis_desc}

## 决策规则
1. 单只股票仓位不超过总资产的 {config.get('single_position_pct', 0.15) * 100:.0f}%
2. 同时持仓不超过 {config.get('max_position_count', 10)} 只
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
        chunks = []
        async for token in llm.chat_stream(messages):
            chunks.append(token)
        raw = "".join(chunks)

        # 解析 JSON
        try:
            # 提取 JSON 部分
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

        return decisions

    # ── Step 4: 自动执行 ──────────────────────────────

    async def _execute_decisions(self, decisions: list[dict]) -> tuple[list[str], list[str]]:
        """执行决策：生成 trade_plan → execute_trade"""
        plan_ids = []
        trade_ids = []
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

                # 卖出/减仓需要找到对应持仓
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

                # 加仓需要找到对应持仓
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
                    holding_type=holding_type if action in ("buy",) else None,
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/test_agent_brain.py::TestBrainCandidates -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/engine/agent/brain.py tests/unit/test_agent_brain.py
git commit -m "feat(brain): AgentBrain 核心决策逻辑 — 筛选+分析+决策+执行"
```

---

### Task 5: scheduler.py — 定时调度

**Files:**
- Create: `backend/engine/agent/scheduler.py`
- Modify: `backend/main.py`

- [ ] **Step 1: 创建 Agent 调度器**

创建 `backend/engine/agent/scheduler.py`：

```python
"""
Agent Brain 定时调度
每个交易日收盘后自动运行 AgentBrain
"""
from __future__ import annotations

import asyncio
from datetime import date

from loguru import logger


class AgentScheduler:
    """Agent Brain 定时调度器"""

    _instance: AgentScheduler | None = None
    _scheduler = None

    @classmethod
    def get_instance(cls) -> AgentScheduler:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._scheduler = None

    def start(self, portfolio_id: str | None = None):
        """启动定时调度"""
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.triggers.cron import CronTrigger

            self._scheduler = AsyncIOScheduler()

            # 每个交易日 15:30 运行
            self._scheduler.add_job(
                self._daily_run,
                CronTrigger(hour=15, minute=30, day_of_week="mon-fri"),
                id="agent_brain_daily",
                args=[portfolio_id],
                replace_existing=True,
            )

            self._scheduler.start()
            logger.info("🧠 Agent Brain 调度器已启动 (每交易日 15:30)")
        except ImportError:
            logger.warning("🧠 APScheduler 未安装，Agent Brain 定时调度不可用")
        except Exception as e:
            logger.warning(f"🧠 Agent Brain 调度器启动失败: {e}")

    async def _daily_run(self, portfolio_id: str | None = None):
        """每日定时运行"""
        # 简单的周末判断
        today = date.today()
        if today.weekday() >= 5:
            logger.info("🧠 今天是周末，跳过 Agent Brain 运行")
            return

        if not portfolio_id:
            # 查找 live 账户
            from engine.agent.db import AgentDB
            from engine.agent.service import AgentService
            from engine.agent.validator import TradeValidator
            db = AgentDB.get_instance()
            svc = AgentService(db=db, validator=TradeValidator())
            portfolios = await svc.list_portfolios()
            live = [p for p in portfolios if p.get("mode") == "live"]
            if not live:
                logger.info("🧠 没有 live 账户，跳过运行")
                return
            portfolio_id = live[0]["id"]

        logger.info(f"🧠 定时运行 AgentBrain: portfolio={portfolio_id}")

        from engine.agent.brain import AgentBrain
        from engine.agent.db import AgentDB
        from engine.agent.service import AgentService
        from engine.agent.validator import TradeValidator

        db = AgentDB.get_instance()
        svc = AgentService(db=db, validator=TradeValidator())
        run_record = await svc.create_brain_run(portfolio_id, "scheduled")

        brain = AgentBrain(portfolio_id)
        await brain.execute(run_record["id"])

    def shutdown(self):
        """关闭调度器"""
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            logger.info("🧠 Agent Brain 调度器已关闭")
```

- [ ] **Step 2: 在 main.py 中注册调度器**

在 `backend/main.py` 的 startup 事件中，AgentDB 初始化之后追加：

```python
    # 启动 Agent Brain 调度器
    try:
        from engine.agent.scheduler import AgentScheduler
        agent_scheduler = AgentScheduler.get_instance()
        agent_scheduler.start()
        logger.info("   Agent Brain 调度器: 已启动")
    except Exception as e:
        logger.warning(f"⚠️ Agent Brain 调度器启动失败: {e}")
```

在 shutdown 事件中追加：

```python
    # 关闭 Agent Brain 调度器
    try:
        from engine.agent.scheduler import AgentScheduler
        AgentScheduler.get_instance().shutdown()
    except Exception:
        pass
```

- [ ] **Step 3: Commit**

```bash
git add backend/engine/agent/scheduler.py backend/main.py
git commit -m "feat(brain): Agent Brain 定时调度器"
```

---

### Task 6: 运行全部后端测试

- [ ] **Step 1: 运行全部测试**

Run: `python3 -m pytest tests/unit/test_agent_brain.py tests/unit/test_trade_plans.py tests/unit/test_agent_phase1a.py -v`
Expected: 全部通过

- [ ] **Step 2: Commit**

```bash
git add -A
git commit -m "feat(brain): Phase 1B-2 后端完整实现"
```

## Chunk 3: 前端 /agent 页面 (Task 7-8)

### Task 7: /agent 页面

**Files:**
- Create: `frontend/app/agent/page.tsx`
- Modify: `frontend/components/ui/NavSidebar.tsx`

- [ ] **Step 1: 创建 /agent 页面**

```bash
mkdir -p frontend/app/agent
```

创建 `frontend/app/agent/page.tsx`：

```tsx
"use client";

import { useState, useEffect, useCallback } from "react";
import NavSidebar from "@/components/ui/NavSidebar";

interface BrainRun {
  id: string;
  portfolio_id: string;
  run_type: string;
  status: string;
  candidates: any[] | null;
  analysis_results: any[] | null;
  decisions: any[] | null;
  plan_ids: string[] | null;
  trade_ids: string[] | null;
  error_message: string | null;
  llm_tokens_used: number;
  started_at: string;
  completed_at: string | null;
}

interface WatchlistItem {
  id: string;
  stock_code: string;
  stock_name: string;
  reason: string | null;
  added_by: string;
  created_at: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function AgentPage() {
  const [runs, setRuns] = useState<BrainRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<BrainRun | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [portfolioId, setPortfolioId] = useState<string | null>(null);
  const [newCode, setNewCode] = useState("");
  const [newName, setNewName] = useState("");

  // 获取 portfolio
  useEffect(() => {
    fetch(`${API_BASE}/api/v1/agent/portfolio`)
      .then((r) => r.json())
      .then((data) => {
        if (data.length > 0) setPortfolioId(data[0].id);
      })
      .catch(() => {});
  }, []);

  // 获取运行记录
  const fetchRuns = useCallback(async () => {
    if (!portfolioId) return;
    setLoading(true);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/agent/brain/runs?portfolio_id=${portfolioId}`);
      if (resp.ok) {
        const data = await resp.json();
        setRuns(data);
        if (data.length > 0 && !selectedRun) setSelectedRun(data[0]);
      }
    } finally {
      setLoading(false);
    }
  }, [portfolioId]);

  useEffect(() => {
    fetchRuns();
  }, [fetchRuns]);

  // 获取关注列表
  const fetchWatchlist = useCallback(async () => {
    const resp = await fetch(`${API_BASE}/api/v1/agent/watchlist`);
    if (resp.ok) setWatchlist(await resp.json());
  }, []);

  useEffect(() => {
    fetchWatchlist();
  }, [fetchWatchlist]);

  // 手动触发运行
  const handleRun = async () => {
    if (!portfolioId || running) return;
    setRunning(true);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/agent/brain/run?portfolio_id=${portfolioId}`, {
        method: "POST",
      });
      if (resp.ok) {
        // 轮询等待完成
        const run = await resp.json();
        setSelectedRun(run);
        const poll = setInterval(async () => {
          const r = await fetch(`${API_BASE}/api/v1/agent/brain/runs/${run.id}`);
          if (r.ok) {
            const updated = await r.json();
            setSelectedRun(updated);
            if (updated.status !== "running") {
              clearInterval(poll);
              setRunning(false);
              fetchRuns();
            }
          }
        }, 3000);
      }
    } catch {
      setRunning(false);
    }
  };

  // 添加关注
  const handleAddWatch = async () => {
    if (!newCode.trim()) return;
    await fetch(`${API_BASE}/api/v1/agent/watchlist`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ stock_code: newCode.trim(), stock_name: newName.trim() || newCode.trim() }),
    });
    setNewCode("");
    setNewName("");
    fetchWatchlist();
  };

  // 删除关注
  const handleRemoveWatch = async (id: string) => {
    await fetch(`${API_BASE}/api/v1/agent/watchlist/${id}`, { method: "DELETE" });
    fetchWatchlist();
  };

  const statusColor: Record<string, string> = {
    running: "bg-blue-500/20 text-blue-400",
    completed: "bg-green-500/20 text-green-400",
    failed: "bg-red-500/20 text-red-400",
  };

  return (
    <div className="flex h-screen bg-[#0a0a0f] text-white">
      <NavSidebar />
      <div className="flex-1 flex flex-col ml-12">
        {/* 顶部状态栏 */}
        <div className="flex items-center justify-between p-4 border-b border-white/10">
          <div className="flex items-center gap-4">
            <h1 className="text-xl font-bold">🤖 Agent Brain</h1>
            {selectedRun && (
              <span className={`px-2 py-0.5 rounded text-xs ${statusColor[selectedRun.status] || ""}`}>
                {selectedRun.status === "running" ? "运行中..." : selectedRun.status}
              </span>
            )}
          </div>
          <button
            onClick={handleRun}
            disabled={running || !portfolioId}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              running
                ? "bg-blue-500/20 text-blue-400 cursor-wait"
                : "bg-white/10 text-white hover:bg-white/20"
            }`}
          >
            {running ? "运行中..." : "▶ 手动运行"}
          </button>
        </div>

        <div className="flex-1 flex overflow-hidden">
          {/* 左侧：运行记录 + 关注列表 */}
          <div className="w-72 border-r border-white/10 flex flex-col">
            {/* 运行记录 */}
            <div className="flex-1 overflow-y-auto">
              <div className="p-3 text-xs text-gray-400 font-medium">运行记录</div>
              {loading ? (
                <div className="text-gray-500 text-center py-4 text-sm">加载中...</div>
              ) : runs.length === 0 ? (
                <div className="text-gray-500 text-center py-4 text-sm">暂无运行记录</div>
              ) : (
                runs.map((run) => (
                  <button
                    key={run.id}
                    onClick={() => setSelectedRun(run)}
                    className={`w-full text-left px-3 py-2 text-sm border-b border-white/5 transition-colors ${
                      selectedRun?.id === run.id ? "bg-white/10" : "hover:bg-white/5"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-gray-300">
                        {new Date(run.started_at).toLocaleDateString()}
                      </span>
                      <span className={`px-1.5 py-0.5 rounded text-xs ${statusColor[run.status] || ""}`}>
                        {run.status}
                      </span>
                    </div>
                    <div className="text-xs text-gray-500 mt-0.5">
                      {run.run_type === "manual" ? "手动" : "定时"}
                      {run.decisions && ` · ${run.decisions.length} 个决策`}
                    </div>
                  </button>
                ))
              )}
            </div>

            {/* 关注列表 */}
            <div className="border-t border-white/10">
              <div className="p-3 text-xs text-gray-400 font-medium">关注列表</div>
              <div className="px-3 pb-2 flex gap-1">
                <input
                  type="text"
                  placeholder="代码"
                  value={newCode}
                  onChange={(e) => setNewCode(e.target.value)}
                  className="bg-white/5 border border-white/10 rounded px-2 py-1 text-xs text-white w-20"
                />
                <input
                  type="text"
                  placeholder="名称"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="bg-white/5 border border-white/10 rounded px-2 py-1 text-xs text-white w-20"
                />
                <button onClick={handleAddWatch} className="bg-white/10 rounded px-2 py-1 text-xs hover:bg-white/20">+</button>
              </div>
              <div className="max-h-40 overflow-y-auto">
                {watchlist.map((w) => (
                  <div key={w.id} className="flex items-center justify-between px-3 py-1 text-xs">
                    <span>
                      <span className="font-mono text-white">{w.stock_code}</span>
                      <span className="text-gray-400 ml-1">{w.stock_name}</span>
                    </span>
                    <button onClick={() => handleRemoveWatch(w.id)} className="text-red-400 hover:text-red-300">×</button>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* 右侧：运行详情 */}
          <div className="flex-1 overflow-y-auto p-6">
            {!selectedRun ? (
              <div className="text-gray-500 text-center py-20">
                {portfolioId ? "选择一条运行记录查看详情，或点击「手动运行」" : "请先创建虚拟账户"}
              </div>
            ) : (
              <div className="space-y-6">
                {/* 运行概览 */}
                <div className="flex items-center gap-4 text-sm text-gray-400">
                  <span>开始: {new Date(selectedRun.started_at).toLocaleString()}</span>
                  {selectedRun.completed_at && (
                    <span>完成: {new Date(selectedRun.completed_at).toLocaleString()}</span>
                  )}
                  {selectedRun.llm_tokens_used > 0 && (
                    <span>Token: {selectedRun.llm_tokens_used}</span>
                  )}
                </div>

                {/* 错误信息 */}
                {selectedRun.error_message && (
                  <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-sm text-red-400">
                    {selectedRun.error_message}
                  </div>
                )}

                {/* 候选标的 */}
                {selectedRun.candidates && selectedRun.candidates.length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium text-gray-300 mb-2">
                      候选标的 ({selectedRun.candidates.length})
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      {selectedRun.candidates.map((c: any, i: number) => (
                        <span key={i} className="px-2 py-1 rounded text-xs bg-white/5 border border-white/10">
                          <span className="font-mono text-white">{c.stock_code}</span>
                          <span className="text-gray-400 ml-1">{c.stock_name}</span>
                          <span className={`ml-1 ${
                            c.source === "position" ? "text-blue-400" :
                            c.source === "watchlist" ? "text-yellow-400" : "text-green-400"
                          }`}>
                            ({c.source})
                          </span>
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* 决策列表 */}
                {selectedRun.decisions && selectedRun.decisions.length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium text-gray-300 mb-2">
                      决策 ({selectedRun.decisions.length})
                    </h3>
                    <div className="space-y-2">
                      {selectedRun.decisions.map((d: any, i: number) => {
                        const isBuy = d.action === "buy" || d.action === "add";
                        return (
                          <div key={i} className={`rounded-lg border p-3 ${
                            isBuy ? "bg-green-500/5 border-green-500/20" : "bg-red-500/5 border-red-500/20"
                          }`}>
                            <div className="flex items-center gap-2 mb-1">
                              <span className="font-mono font-bold text-white">{d.stock_code}</span>
                              <span className="text-gray-300">{d.stock_name}</span>
                              <span className={`px-1.5 py-0.5 rounded text-xs font-bold ${
                                isBuy ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"
                              }`}>
                                {d.action}
                              </span>
                              {d.confidence && (
                                <span className="text-xs text-gray-500">信心: {(d.confidence * 100).toFixed(0)}%</span>
                              )}
                            </div>
                            <div className="text-sm text-gray-300 grid grid-cols-2 md:grid-cols-4 gap-2">
                              {d.price && <div>价格: <span className="text-white">{d.price}</span></div>}
                              {d.quantity && <div>数量: <span className="text-white">{d.quantity}</span></div>}
                              {d.take_profit && <div>止盈: <span className="text-green-400">{d.take_profit}</span></div>}
                              {d.stop_loss && <div>止损: <span className="text-red-400">{d.stop_loss}</span></div>}
                            </div>
                            {d.reasoning && (
                              <div className="text-xs text-gray-400 mt-1">{d.reasoning}</div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* 执行结果 */}
                {selectedRun.plan_ids && selectedRun.plan_ids.length > 0 && (
                  <div className="text-sm text-gray-400">
                    生成 {selectedRun.plan_ids.length} 个交易计划，
                    执行 {selectedRun.trade_ids?.length || 0} 笔交易
                  </div>
                )}

                {/* 分析摘要 */}
                {selectedRun.analysis_results && selectedRun.analysis_results.length > 0 && (
                  <details className="group">
                    <summary className="text-sm font-medium text-gray-300 cursor-pointer hover:text-white">
                      分析详情 ({selectedRun.analysis_results.length} 只) ▸
                    </summary>
                    <div className="mt-2 space-y-2 max-h-96 overflow-y-auto">
                      {selectedRun.analysis_results.map((a: any, i: number) => (
                        <div key={i} className="bg-white/5 rounded p-2 text-xs">
                          <div className="font-mono text-white mb-1">{a.stock_code} {a.stock_name}</div>
                          {a.error ? (
                            <div className="text-red-400">{a.error}</div>
                          ) : (
                            <pre className="text-gray-400 whitespace-pre-wrap overflow-hidden max-h-32">
                              {typeof a.daily === "string" ? a.daily.slice(0, 300) : JSON.stringify(a.daily, null, 1)?.slice(0, 300)}
                            </pre>
                          )}
                        </div>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 在 NavSidebar 中新增 /agent 导航项**

在 `frontend/components/ui/NavSidebar.tsx` 中：

1. import 新增 `Bot`：
```tsx
import { Mountain, Scale, BrainCircuit, TrendingUp, ClipboardList, GitBranch, FileText, Bot } from "lucide-react";
```

2. NAV_ITEMS 中在 "交易计划" 之后新增：
```tsx
{ href: "/agent", icon: Bot, label: "Agent" },
```

- [ ] **Step 3: 验证前端编译**

Run: `cd frontend && npx tsc --noEmit 2>&1 | grep -E "(agent/page|NavSidebar)" | head -10`
Expected: 无我们新增文件的错误

- [ ] **Step 4: Commit**

```bash
git add frontend/app/agent/page.tsx frontend/components/ui/NavSidebar.tsx
git commit -m "feat(brain): /agent 页面 + 导航栏入口"
```

---

### Task 8: 最终验证

- [ ] **Step 1: 运行全部后端测试**

Run: `python3 -m pytest tests/unit/test_agent_brain.py tests/unit/test_trade_plans.py tests/unit/test_agent_phase1a.py -v`
Expected: 全部通过

- [ ] **Step 2: 验证前端类型检查**

Run: `cd frontend && npx tsc --noEmit 2>&1 | grep -v "SectorTrendChart" | head -20`
Expected: 无新增错误

- [ ] **Step 3: 最终 Commit**

```bash
git add -A
git commit -m "feat: Phase 1B-2 Agent Brain 完整实现"
```
