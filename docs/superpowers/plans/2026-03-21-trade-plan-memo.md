# 交易计划备忘录 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让专家对话中 AI 给出的交易建议可以一键收藏为结构化的交易计划备忘录。

**Architecture:** 后端复用 AgentDB 新增 trade_plans 表 + 5 个 CRUD API。修改专家对话 system prompt 约定交易计划输出格式。前端在 MessageBubble 中解析 `【交易计划】` 块渲染卡片，新增 `/plans` 页签展示备忘录。

**Tech Stack:** Python/FastAPI/DuckDB (后端), Next.js/React/TypeScript (前端)

**Spec:** `docs/superpowers/specs/2026-03-21-trade-plan-memo-design.md`

---

## File Structure

```
backend/
├── engine/agent/
│   ├── db.py                          ← 修改: _init_tables 新增 trade_plans 表
│   ├── models.py                      ← 修改: 新增 TradePlan, TradePlanInput, TradePlanUpdate
│   ├── service.py                     ← 修改: 新增 plans CRUD 方法
│   └── routes.py                      ← 修改: 新增 5 个 plans API 端点
├── engine/expert/
│   └── engine_experts.py              ← 修改: system prompt 追加交易计划格式约定

tests/unit/
└── test_trade_plans.py                ← 新建: 交易计划后端测试

frontend/
├── components/ui/
│   └── NavSidebar.tsx                 ← 修改: 新增 /plans 导航项
├── components/expert/
│   └── MessageBubble.tsx              ← 修改: 解析交易计划块 + 渲染卡片
├── components/plans/
│   └── TradePlanCard.tsx              ← 新建: 交易计划卡片组件
├── app/plans/
│   └── page.tsx                       ← 新建: 备忘页签页面
└── lib/
    └── parseTradePlan.ts              ← 新建: 交易计划解析工具函数
```

---

## Chunk 1: 后端 (Task 1-4)

### Task 1: trade_plans 表 + 数据模型

**Files:**
- Modify: `backend/engine/agent/db.py` (_init_tables 方法)
- Modify: `backend/engine/agent/models.py`
- Test: `tests/unit/test_trade_plans.py`

- [ ] **Step 1: 写 trade_plans 表创建的失败测试**

创建 `tests/unit/test_trade_plans.py`：

```python
"""交易计划备忘录单元测试"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

import asyncio
import duckdb
import pytest
from unittest.mock import patch

def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ═══════════════════════════════════════════════════════
# Task 1: trade_plans 表 + 模型
# ═══════════════════════════════════════════════════════

class TestTradePlansTable:
    """trade_plans 表测试"""

    def test_table_exists(self, tmp_path):
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

        assert "trade_plans" in table_names


class TestTradePlanModels:
    """Pydantic 模型测试"""

    def test_trade_plan_input_valid(self):
        from engine.agent.models import TradePlanInput
        ti = TradePlanInput(
            stock_code="600519", stock_name="贵州茅台",
            current_price=1800.0, direction="buy",
            entry_price=1750.0, entry_method="分两批买入",
            position_pct=0.1,
            take_profit=2100.0, take_profit_method="到2000先减半，2100清仓",
            stop_loss=1650.0, stop_loss_method="跌破1650一次性清仓",
            reasoning="白酒消费复苏",
            risk_note="消费数据不及预期",
            invalidation="Q2营收下滑",
            valid_until="2026-04",
        )
        assert ti.direction == "buy"
        assert ti.source_type == "expert"

    def test_trade_plan_input_minimal(self):
        from engine.agent.models import TradePlanInput
        ti = TradePlanInput(
            stock_code="600519", stock_name="贵州茅台",
            direction="buy", reasoning="白酒龙头",
        )
        assert ti.entry_price is None
        assert ti.stop_loss is None

    def test_trade_plan_update(self):
        from engine.agent.models import TradePlanUpdate
        u = TradePlanUpdate(status="executing")
        assert u.status == "executing"

    def test_trade_plan_update_invalid_status(self):
        from engine.agent.models import TradePlanUpdate
        with pytest.raises(Exception):
            TradePlanUpdate(status="invalid_status")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/test_trade_plans.py -v`
Expected: FAIL — `trade_plans` not in table_names / `TradePlanInput` not found

- [ ] **Step 3: 在 db.py _init_tables 中新增 trade_plans 表**

在 `backend/engine/agent/db.py` 的 `_init_tables` 方法末尾（llm_calls 表之后）追加：

```python
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS agent.trade_plans (
                id VARCHAR PRIMARY KEY,
                stock_code VARCHAR NOT NULL,
                stock_name VARCHAR NOT NULL,
                current_price DOUBLE,
                direction VARCHAR NOT NULL,
                entry_price DOUBLE,
                entry_method TEXT,
                position_pct DOUBLE,
                take_profit DOUBLE,
                take_profit_method TEXT,
                stop_loss DOUBLE,
                stop_loss_method TEXT,
                reasoning TEXT NOT NULL,
                risk_note TEXT,
                invalidation TEXT,
                valid_until DATE,
                status VARCHAR DEFAULT 'pending',
                source_type VARCHAR DEFAULT 'expert',
                source_conversation_id VARCHAR,
                created_at TIMESTAMP DEFAULT now(),
                updated_at TIMESTAMP DEFAULT now()
            )
        """)
```

- [ ] **Step 4: 在 models.py 中新增 TradePlan 模型**

在 `backend/engine/agent/models.py` 末尾追加：

```python
# ── 交易计划备忘录 ────────────────────────────────────

class TradePlan(BaseModel):
    id: str
    stock_code: str
    stock_name: str
    current_price: float | None = None
    direction: Literal["buy", "sell"]
    entry_price: float | None = None
    entry_method: str | None = None
    position_pct: float | None = None
    take_profit: float | None = None
    take_profit_method: str | None = None
    stop_loss: float | None = None
    stop_loss_method: str | None = None
    reasoning: str
    risk_note: str | None = None
    invalidation: str | None = None
    valid_until: str | None = None
    status: Literal["pending", "executing", "completed", "expired", "ignored"] = "pending"
    source_type: Literal["expert", "agent", "manual"] = "expert"
    source_conversation_id: str | None = None
    created_at: str
    updated_at: str


class TradePlanInput(BaseModel):
    stock_code: str
    stock_name: str
    current_price: float | None = None
    direction: Literal["buy", "sell"]
    entry_price: float | None = None
    entry_method: str | None = None
    position_pct: float | None = None
    take_profit: float | None = None
    take_profit_method: str | None = None
    stop_loss: float | None = None
    stop_loss_method: str | None = None
    reasoning: str
    risk_note: str | None = None
    invalidation: str | None = None
    valid_until: str | None = None
    source_type: Literal["expert", "agent", "manual"] = "expert"
    source_conversation_id: str | None = None


class TradePlanUpdate(BaseModel):
    status: Literal["pending", "executing", "completed", "expired", "ignored"] | None = None
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/test_trade_plans.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add backend/engine/agent/db.py backend/engine/agent/models.py tests/unit/test_trade_plans.py
git commit -m "feat(plans): trade_plans 表 + Pydantic 模型"
```

---

### Task 2: Service 层 — Plans CRUD

**Files:**
- Modify: `backend/engine/agent/service.py`
- Test: `tests/unit/test_trade_plans.py` (追加)

- [ ] **Step 1: 写 Plans CRUD 的失败测试**

在 `tests/unit/test_trade_plans.py` 末尾追加：

```python
# ═══════════════════════════════════════════════════════
# Task 2: Plans CRUD Service
# ═══════════════════════════════════════════════════════
import tempfile

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


def _make_plan_input(**overrides):
    from engine.agent.models import TradePlanInput
    defaults = dict(
        stock_code="600519", stock_name="贵州茅台",
        current_price=1800.0, direction="buy",
        entry_price=1750.0, entry_method="分两批买入",
        position_pct=0.1,
        take_profit=2100.0, take_profit_method="到2000先减半",
        stop_loss=1650.0, stop_loss_method="跌破1650清仓",
        reasoning="白酒消费复苏",
        risk_note="消费不及预期",
        invalidation="Q2营收下滑",
        valid_until="2026-04-05",
    )
    defaults.update(overrides)
    return TradePlanInput(**defaults)


class TestServicePlans:
    """AgentService 交易计划 CRUD 测试"""

    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.db, self.svc = _make_service(self._tmp)

    def teardown_method(self):
        self.db.close()

    def test_create_plan(self):
        pi = _make_plan_input()
        result = run(self.svc.create_plan(pi))
        assert result["stock_code"] == "600519"
        assert result["status"] == "pending"
        assert result["id"] is not None

    def test_list_plans(self):
        run(self.svc.create_plan(_make_plan_input()))
        run(self.svc.create_plan(_make_plan_input(stock_code="601318", stock_name="中国平安")))
        result = run(self.svc.list_plans())
        assert len(result) == 2

    def test_list_plans_filter_status(self):
        run(self.svc.create_plan(_make_plan_input()))
        run(self.svc.create_plan(_make_plan_input(stock_code="601318", stock_name="中国平安")))
        # 更新一个为 executing
        plans = run(self.svc.list_plans())
        run(self.svc.update_plan(plans[0]["id"], {"status": "executing"}))
        result = run(self.svc.list_plans(status="pending"))
        assert len(result) == 1

    def test_list_plans_filter_stock_code(self):
        run(self.svc.create_plan(_make_plan_input()))
        run(self.svc.create_plan(_make_plan_input(stock_code="601318", stock_name="中国平安")))
        result = run(self.svc.list_plans(stock_code="600519"))
        assert len(result) == 1

    def test_get_plan(self):
        created = run(self.svc.create_plan(_make_plan_input()))
        result = run(self.svc.get_plan(created["id"]))
        assert result["stock_code"] == "600519"
        assert result["reasoning"] == "白酒消费复苏"

    def test_get_plan_not_found(self):
        with pytest.raises(ValueError, match="不存在"):
            run(self.svc.get_plan("nonexistent"))

    def test_update_plan_status(self):
        created = run(self.svc.create_plan(_make_plan_input()))
        result = run(self.svc.update_plan(created["id"], {"status": "executing"}))
        assert result["status"] == "executing"

    def test_delete_plan(self):
        created = run(self.svc.create_plan(_make_plan_input()))
        run(self.svc.delete_plan(created["id"]))
        with pytest.raises(ValueError, match="不存在"):
            run(self.svc.get_plan(created["id"]))

    def test_delete_plan_not_found(self):
        with pytest.raises(ValueError, match="不存在"):
            run(self.svc.delete_plan("nonexistent"))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/test_trade_plans.py::TestServicePlans -v`
Expected: FAIL — `AttributeError: 'AgentService' object has no attribute 'create_plan'`

- [ ] **Step 3: 在 service.py 中追加 Plans CRUD 方法**

在 `AgentService` 类末尾追加：

```python
    # ── Plans CRUD ────────────────────────────────────

    async def create_plan(self, plan_input: "TradePlanInput") -> dict:
        """创建交易计划"""
        from engine.agent.models import TradePlanInput
        plan_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        await self.db.execute_write(
            """INSERT INTO agent.trade_plans
               (id, stock_code, stock_name, current_price, direction,
                entry_price, entry_method, position_pct,
                take_profit, take_profit_method, stop_loss, stop_loss_method,
                reasoning, risk_note, invalidation, valid_until,
                status, source_type, source_conversation_id,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)""",
            [plan_id, plan_input.stock_code, plan_input.stock_name,
             plan_input.current_price, plan_input.direction,
             plan_input.entry_price, plan_input.entry_method, plan_input.position_pct,
             plan_input.take_profit, plan_input.take_profit_method,
             plan_input.stop_loss, plan_input.stop_loss_method,
             plan_input.reasoning, plan_input.risk_note, plan_input.invalidation,
             plan_input.valid_until,
             plan_input.source_type, plan_input.source_conversation_id,
             now, now],
        )
        rows = await self.db.execute_read(
            "SELECT * FROM agent.trade_plans WHERE id = ?", [plan_id]
        )
        return rows[0]

    async def list_plans(
        self, status: str | None = None, stock_code: str | None = None
    ) -> list[dict]:
        """列出交易计划"""
        sql = "SELECT * FROM agent.trade_plans WHERE 1=1"
        params = []
        if status:
            sql += " AND status = ?"
            params.append(status)
        if stock_code:
            sql += " AND stock_code = ?"
            params.append(stock_code)
        sql += " ORDER BY created_at DESC"
        return await self.db.execute_read(sql, params if params else None)

    async def get_plan(self, plan_id: str) -> dict:
        """获取单个交易计划"""
        rows = await self.db.execute_read(
            "SELECT * FROM agent.trade_plans WHERE id = ?", [plan_id]
        )
        if not rows:
            raise ValueError(f"交易计划 {plan_id} 不存在")
        return rows[0]

    async def update_plan(self, plan_id: str, updates: dict) -> dict:
        """更新交易计划"""
        await self.get_plan(plan_id)  # 确认存在
        now = datetime.now().isoformat()
        if "status" in updates and updates["status"]:
            await self.db.execute_write(
                "UPDATE agent.trade_plans SET status = ?, updated_at = ? WHERE id = ?",
                [updates["status"], now, plan_id],
            )
        return await self.get_plan(plan_id)

    async def delete_plan(self, plan_id: str):
        """删除交易计划"""
        await self.get_plan(plan_id)  # 确认存在
        await self.db.execute_write(
            "DELETE FROM agent.trade_plans WHERE id = ?", [plan_id]
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/test_trade_plans.py::TestServicePlans -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add backend/engine/agent/service.py tests/unit/test_trade_plans.py
git commit -m "feat(plans): Plans CRUD service 层 + 单元测试"
```

---

### Task 3: FastAPI 路由 — Plans API

**Files:**
- Modify: `backend/engine/agent/routes.py`
- Test: `tests/unit/test_trade_plans.py` (追加)

- [ ] **Step 1: 写路由的失败测试**

在 `tests/unit/test_trade_plans.py` 末尾追加：

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


class TestPlansRoutes:
    """Plans API 路由测试"""

    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self.app, self.db = _create_test_app(self._tmp)
        self.client = TestClient(self.app)

    def teardown_method(self):
        self.db.close()

    def _create_plan(self, **overrides):
        defaults = {
            "stock_code": "600519", "stock_name": "贵州茅台",
            "current_price": 1800.0, "direction": "buy",
            "entry_price": 1750.0, "reasoning": "白酒消费复苏",
            "stop_loss": 1650.0,
        }
        defaults.update(overrides)
        return self.client.post("/api/v1/agent/plans", json=defaults)

    def test_create_plan(self):
        resp = self._create_plan()
        assert resp.status_code == 200
        assert resp.json()["stock_code"] == "600519"
        assert resp.json()["status"] == "pending"

    def test_list_plans(self):
        self._create_plan()
        self._create_plan(stock_code="601318", stock_name="中国平安")
        resp = self.client.get("/api/v1/agent/plans")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_plans_filter_status(self):
        r = self._create_plan()
        plan_id = r.json()["id"]
        self.client.patch(f"/api/v1/agent/plans/{plan_id}", json={"status": "executing"})
        self._create_plan(stock_code="601318", stock_name="中国平安")
        resp = self.client.get("/api/v1/agent/plans?status=pending")
        assert len(resp.json()) == 1

    def test_get_plan(self):
        r = self._create_plan()
        plan_id = r.json()["id"]
        resp = self.client.get(f"/api/v1/agent/plans/{plan_id}")
        assert resp.status_code == 200
        assert resp.json()["stock_code"] == "600519"

    def test_get_plan_404(self):
        resp = self.client.get("/api/v1/agent/plans/nonexistent")
        assert resp.status_code == 404

    def test_update_plan(self):
        r = self._create_plan()
        plan_id = r.json()["id"]
        resp = self.client.patch(f"/api/v1/agent/plans/{plan_id}", json={"status": "executing"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "executing"

    def test_delete_plan(self):
        r = self._create_plan()
        plan_id = r.json()["id"]
        resp = self.client.delete(f"/api/v1/agent/plans/{plan_id}")
        assert resp.status_code == 200
        resp = self.client.get(f"/api/v1/agent/plans/{plan_id}")
        assert resp.status_code == 404

    def test_delete_plan_404(self):
        resp = self.client.delete("/api/v1/agent/plans/nonexistent")
        assert resp.status_code == 404
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/unit/test_trade_plans.py::TestPlansRoutes -v`
Expected: FAIL — 路由不存在，返回 404/405

- [ ] **Step 3: 在 routes.py 中新增 Plans 端点**

在 `backend/engine/agent/routes.py` 中：

1. 在文件顶部 import 区新增：
```python
from engine.agent.models import TradeInput, TradePlanInput, TradePlanUpdate
```

2. 在 `create_agent_router()` 函数内，`return router` 之前追加：

```python
    # ── Plans ──

    @router.post("/plans")
    async def create_plan(req: TradePlanInput):
        svc = _get_service()
        return await svc.create_plan(req)

    @router.get("/plans")
    async def list_plans(
        status: str | None = None,
        stock_code: str | None = None,
    ):
        svc = _get_service()
        return await svc.list_plans(status, stock_code)

    @router.get("/plans/{plan_id}")
    async def get_plan(plan_id: str):
        svc = _get_service()
        try:
            return await svc.get_plan(plan_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.patch("/plans/{plan_id}")
    async def update_plan(plan_id: str, req: TradePlanUpdate):
        svc = _get_service()
        try:
            return await svc.update_plan(plan_id, req.model_dump(exclude_none=True))
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.delete("/plans/{plan_id}")
    async def delete_plan(plan_id: str):
        svc = _get_service()
        try:
            await svc.delete_plan(plan_id)
            return {"ok": True}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/unit/test_trade_plans.py::TestPlansRoutes -v`
Expected: 8 passed

- [ ] **Step 5: 运行全部 trade_plans 测试**

Run: `python3 -m pytest tests/unit/test_trade_plans.py -v`
Expected: 全部通过（约 21 个）

- [ ] **Step 6: Commit**

```bash
git add backend/engine/agent/routes.py tests/unit/test_trade_plans.py
git commit -m "feat(plans): Plans API 5 个端点 + 路由测试"
```

---

### Task 4: 专家对话 Prompt 注入

**Files:**
- Modify: `backend/engine/expert/engine_experts.py`

- [ ] **Step 1: 读取 engine_experts.py 了解 system prompt 拼装位置**

Run: 读取 `backend/engine/expert/engine_experts.py` 中 `_reply_stream` 和 `_retry_reply_non_stream` 方法的 system prompt 拼装逻辑。

- [ ] **Step 2: 创建交易计划 prompt 片段**

在 `backend/engine/expert/engine_experts.py` 文件顶部（EXPERT_PROFILES 之前）新增常量：

```python
# ── 交易计划输出格式约定 ──
TRADE_PLAN_PROMPT = """

## 交易计划输出规则

当你认为应该给出具体的股票操作建议时，请在回复末尾用以下固定格式输出交易计划。
注意：只有当你有足够信心给出完整操作方案时才输出，不要在随意讨论中输出。

格式（必须严格遵守，前端会解析）：

【交易计划】
标的：{代码} {名称}
当前价格：{现价}
方向：{买入/卖出}
建议价格：{目标进场价}
买入方式：{分批策略描述}
仓位建议：{占总仓位百分比}
止盈目标：{止盈价}
止盈方式：{止盈执行策略}
止损价格：{止损价}
止损方式：{止损执行策略}
理由：{核心逻辑}
风险提示：{主要风险}
失效条件：{什么情况下应该放弃这个计划}
有效期：{YYYY-MM 或具体日期}
【/交易计划】

标的、方向、建议价格、止损价格、理由为必填。其余字段根据情况填写。
"""
```

- [ ] **Step 3: 在 system prompt 拼装处追加 TRADE_PLAN_PROMPT**

找到 `_reply_stream` 和 `_retry_reply_non_stream` 方法中拼装 system prompt 的位置，在末尾追加：

```python
system = self.profile["system_prompt"] + f"\n⏰ 当前时间：{get_current_date_context()}"
system += "\n\n⚠️ 重要：你的所有数据通过工具从数据源实时拉取..."
system += TRADE_PLAN_PROMPT  # ← 新增这一行
```

同样在 `_plan_tools_native` 方法中也追加（如果该方法也拼装 system prompt）。

- [ ] **Step 4: 验证 import 正常**

Run: `cd backend && python3 -c "from engine.expert.engine_experts import TRADE_PLAN_PROMPT; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add backend/engine/expert/engine_experts.py
git commit -m "feat(plans): 专家对话 system prompt 追加交易计划格式约定"
```

## Chunk 2: 前端 (Task 5-8)

### Task 5: 交易计划解析工具函数

**Files:**
- Create: `frontend/lib/parseTradePlan.ts`

- [ ] **Step 1: 创建解析工具函数**

创建 `frontend/lib/parseTradePlan.ts`：

```typescript
/**
 * 解析 AI 回复中的【交易计划】块
 */

export interface TradePlanData {
  stock_code: string;
  stock_name: string;
  current_price: number | null;
  direction: "buy" | "sell";
  entry_price: number | null;
  entry_method: string | null;
  position_pct: number | null;
  take_profit: number | null;
  take_profit_method: string | null;
  stop_loss: number | null;
  stop_loss_method: string | null;
  reasoning: string;
  risk_note: string | null;
  invalidation: string | null;
  valid_until: string | null;
}

const PLAN_REGEX = /【交易计划】([\s\S]*?)【\/交易计划】/g;

const KEY_MAP: Record<string, keyof TradePlanData> = {
  "标的": "stock_code", // 特殊处理：拆分为 code + name
  "当前价格": "current_price",
  "方向": "direction",
  "建议价格": "entry_price",
  "买入方式": "entry_method",
  "仓位建议": "position_pct",
  "止盈目标": "take_profit",
  "止盈方式": "take_profit_method",
  "止损价格": "stop_loss",
  "止损方式": "stop_loss_method",
  "理由": "reasoning",
  "风险提示": "risk_note",
  "失效条件": "invalidation",
  "有效期": "valid_until",
};

function parseFloat2(s: string): number | null {
  const n = parseFloat(s);
  return isNaN(n) ? null : n;
}

function parseSinglePlan(block: string): TradePlanData | null {
  const lines = block.trim().split("\n");
  const raw: Record<string, string> = {};

  for (const line of lines) {
    const match = line.match(/^(.+?)：(.+)$/);
    if (match) {
      raw[match[1].trim()] = match[2].trim();
    }
  }

  // 必填字段检查
  if (!raw["标的"] || !raw["方向"] || !raw["理由"]) return null;

  // 拆分标的
  const parts = raw["标的"].split(/\s+/);
  const stock_code = parts[0] || "";
  const stock_name = parts.slice(1).join(" ") || stock_code;

  // 解析仓位百分比（"10%" → 0.1）
  let position_pct: number | null = null;
  if (raw["仓位建议"]) {
    const pctMatch = raw["仓位建议"].match(/([\d.]+)/);
    if (pctMatch) {
      position_pct = parseFloat(pctMatch[1]) / 100;
    }
  }

  return {
    stock_code,
    stock_name,
    current_price: raw["当前价格"] ? parseFloat2(raw["当前价格"]) : null,
    direction: raw["方向"] === "卖出" ? "sell" : "buy",
    entry_price: raw["建议价格"] ? parseFloat2(raw["建议价格"]) : null,
    entry_method: raw["买入方式"] || null,
    position_pct,
    take_profit: raw["止盈目标"] ? parseFloat2(raw["止盈目标"]) : null,
    take_profit_method: raw["止盈方式"] || null,
    stop_loss: raw["止损价格"] ? parseFloat2(raw["止损价格"]) : null,
    stop_loss_method: raw["止损方式"] || null,
    reasoning: raw["理由"] || "",
    risk_note: raw["风险提示"] || null,
    invalidation: raw["失效条件"] || null,
    valid_until: raw["有效期"] || null,
  };
}

/**
 * 从 AI 回复文本中提取所有交易计划
 */
export function extractTradePlans(text: string): TradePlanData[] {
  const plans: TradePlanData[] = [];
  let match;
  while ((match = PLAN_REGEX.exec(text)) !== null) {
    const plan = parseSinglePlan(match[1]);
    if (plan) plans.push(plan);
  }
  return plans;
}

/**
 * 判断文本是否包含交易计划块
 */
export function hasTradePlan(text: string): boolean {
  return /【交易计划】/.test(text) && /【\/交易计划】/.test(text);
}

/**
 * 将文本按交易计划块拆分为普通文本和计划块交替的数组
 */
export function splitByTradePlan(
  text: string
): Array<{ type: "text" | "plan"; content: string; plan?: TradePlanData }> {
  const result: Array<{ type: "text" | "plan"; content: string; plan?: TradePlanData }> = [];
  const regex = /【交易计划】([\s\S]*?)【\/交易计划】/g;
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(text)) !== null) {
    // 计划块之前的普通文本
    if (match.index > lastIndex) {
      result.push({ type: "text", content: text.slice(lastIndex, match.index) });
    }
    // 计划块
    const plan = parseSinglePlan(match[1]);
    result.push({
      type: "plan",
      content: match[0],
      plan: plan || undefined,
    });
    lastIndex = match.index + match[0].length;
  }

  // 剩余文本
  if (lastIndex < text.length) {
    result.push({ type: "text", content: text.slice(lastIndex) });
  }

  return result;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/lib/parseTradePlan.ts
git commit -m "feat(plans): 交易计划解析工具函数"
```

---

### Task 6: TradePlanCard 组件

**Files:**
- Create: `frontend/components/plans/TradePlanCard.tsx`

- [ ] **Step 1: 创建卡片组件**

```bash
mkdir -p frontend/components/plans
```

创建 `frontend/components/plans/TradePlanCard.tsx`：

```tsx
"use client";

import { useState } from "react";
import { TradePlanData } from "@/lib/parseTradePlan";

interface TradePlanCardProps {
  plan: TradePlanData;
  /** 收藏模式：对话中显示收藏按钮 */
  onSave?: (plan: TradePlanData) => Promise<void>;
  /** 管理模式：备忘页中显示状态管理 */
  savedPlan?: {
    id: string;
    status: string;
    created_at: string;
  };
  onStatusChange?: (id: string, status: string) => Promise<void>;
  onDelete?: (id: string) => Promise<void>;
}

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  pending: { label: "待执行", color: "bg-yellow-500/20 text-yellow-400" },
  executing: { label: "执行中", color: "bg-blue-500/20 text-blue-400" },
  completed: { label: "已完成", color: "bg-green-500/20 text-green-400" },
  expired: { label: "已过期", color: "bg-gray-500/20 text-gray-400" },
  ignored: { label: "已忽略", color: "bg-gray-500/20 text-gray-400" },
};

export default function TradePlanCard({
  plan,
  onSave,
  savedPlan,
  onStatusChange,
  onDelete,
}: TradePlanCardProps) {
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  const isBuy = plan.direction === "buy";
  const dirLabel = isBuy ? "买入" : "卖出";
  const dirColor = isBuy ? "text-green-400" : "text-red-400";
  const dirBg = isBuy ? "bg-green-500/10 border-green-500/30" : "bg-red-500/10 border-red-500/30";

  const handleSave = async () => {
    if (!onSave || saved || saving) return;
    setSaving(true);
    try {
      await onSave(plan);
      setSaved(true);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className={`rounded-lg border p-4 ${dirBg} space-y-3`}>
      {/* 顶部：标的 + 方向 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-mono font-bold text-white">{plan.stock_code}</span>
          <span className="text-gray-300">{plan.stock_name}</span>
          <span className={`px-2 py-0.5 rounded text-xs font-bold ${dirColor} ${isBuy ? "bg-green-500/20" : "bg-red-500/20"}`}>
            {dirLabel}
          </span>
        </div>
        {savedPlan && (
          <span className={`px-2 py-0.5 rounded text-xs ${STATUS_LABELS[savedPlan.status]?.color || ""}`}>
            {STATUS_LABELS[savedPlan.status]?.label || savedPlan.status}
          </span>
        )}
      </div>

      {/* 三栏内容 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
        {/* 进场策略 */}
        <div className="space-y-1">
          <div className="text-gray-400 font-medium text-xs">进场策略</div>
          {plan.current_price && <div>现价：<span className="text-white">{plan.current_price}</span></div>}
          {plan.entry_price && <div>建议价：<span className="text-white">{plan.entry_price}</span></div>}
          {plan.entry_method && <div className="text-gray-300">{plan.entry_method}</div>}
          {plan.position_pct && <div>仓位：<span className="text-white">{(plan.position_pct * 100).toFixed(0)}%</span></div>}
        </div>

        {/* 离场策略 */}
        <div className="space-y-1">
          <div className="text-gray-400 font-medium text-xs">离场策略</div>
          {plan.take_profit && <div>止盈：<span className="text-green-400">{plan.take_profit}</span></div>}
          {plan.take_profit_method && <div className="text-gray-300">{plan.take_profit_method}</div>}
          {plan.stop_loss && <div>止损：<span className="text-red-400">{plan.stop_loss}</span></div>}
          {plan.stop_loss_method && <div className="text-gray-300">{plan.stop_loss_method}</div>}
        </div>

        {/* 理由 */}
        <div className="space-y-1">
          <div className="text-gray-400 font-medium text-xs">理由</div>
          <div className="text-gray-200">{plan.reasoning}</div>
          {plan.risk_note && <div className="text-yellow-400/80 text-xs">⚠️ {plan.risk_note}</div>}
          {plan.invalidation && <div className="text-red-400/80 text-xs">❌ {plan.invalidation}</div>}
        </div>
      </div>

      {/* 底部：有效期 + 操作按钮 */}
      <div className="flex items-center justify-between pt-2 border-t border-white/10">
        <div className="text-xs text-gray-500">
          {plan.valid_until && <span>有效期：{plan.valid_until}</span>}
          {savedPlan?.created_at && <span className="ml-3">创建：{new Date(savedPlan.created_at).toLocaleDateString()}</span>}
        </div>
        <div className="flex gap-2">
          {/* 对话模式：收藏按钮 */}
          {onSave && !savedPlan && (
            <button
              onClick={handleSave}
              disabled={saved || saving}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                saved
                  ? "bg-green-500/20 text-green-400 cursor-default"
                  : "bg-white/10 text-white hover:bg-white/20"
              }`}
            >
              {saved ? "已收藏 ✓" : saving ? "收藏中..." : "📋 收藏到备忘录"}
            </button>
          )}
          {/* 管理模式：状态切换 */}
          {savedPlan && onStatusChange && (
            <select
              value={savedPlan.status}
              onChange={(e) => onStatusChange(savedPlan.id, e.target.value)}
              className="bg-white/10 text-white text-xs rounded px-2 py-1 border border-white/20"
            >
              <option value="pending">待执行</option>
              <option value="executing">执行中</option>
              <option value="completed">已完成</option>
              <option value="expired">已过期</option>
              <option value="ignored">已忽略</option>
            </select>
          )}
          {savedPlan && onDelete && (
            <button
              onClick={() => onDelete(savedPlan.id)}
              className="px-2 py-1 rounded text-xs text-red-400 hover:bg-red-500/20"
            >
              删除
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/plans/TradePlanCard.tsx
git commit -m "feat(plans): TradePlanCard 交易计划卡片组件"
```

---

### Task 7: MessageBubble 集成交易计划卡片

**Files:**
- Modify: `frontend/components/expert/MessageBubble.tsx`

- [ ] **Step 1: 读取 MessageBubble.tsx 了解当前结构**

读取 `frontend/components/expert/MessageBubble.tsx` 全文，了解 `MarkdownContent` 函数和消息渲染逻辑。

- [ ] **Step 2: 修改 MessageBubble 集成交易计划解析**

在 MessageBubble.tsx 中：

1. 顶部新增 import：
```tsx
import { splitByTradePlan, hasTradePlan, TradePlanData } from "@/lib/parseTradePlan";
import TradePlanCard from "@/components/plans/TradePlanCard";
```

2. 在 AI 消息渲染部分，将原来直接渲染 `<MarkdownContent content={msg.content} />` 的逻辑改为：

```tsx
{/* AI 消息内容 — 检测交易计划块 */}
{hasTradePlan(msg.content) ? (
  splitByTradePlan(msg.content).map((segment, i) =>
    segment.type === "text" ? (
      <MarkdownContent key={i} content={segment.content} />
    ) : segment.plan ? (
      <div key={i} className="my-3">
        <TradePlanCard
          plan={segment.plan}
          onSave={async (plan) => {
            await fetch("/api/v1/agent/plans", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(plan),
            });
          }}
        />
      </div>
    ) : (
      <MarkdownContent key={i} content={segment.content} />
    )
  )
) : (
  <MarkdownContent content={msg.content} />
)}
```

具体插入位置需要根据 MessageBubble.tsx 的实际结构调整。关键是只修改 AI 消息（role === "assistant"）的渲染路径。

- [ ] **Step 3: 验证前端编译通过**

Run: `cd frontend && npm run build` (或 `npx next build`)
Expected: 编译成功，无类型错误

- [ ] **Step 4: Commit**

```bash
git add frontend/components/expert/MessageBubble.tsx
git commit -m "feat(plans): MessageBubble 集成交易计划卡片渲染"
```

---

### Task 8: 备忘页签 /plans

**Files:**
- Create: `frontend/app/plans/page.tsx`
- Modify: `frontend/components/ui/NavSidebar.tsx`

- [ ] **Step 1: 创建 /plans 页面**

```bash
mkdir -p frontend/app/plans
```

创建 `frontend/app/plans/page.tsx`：

```tsx
"use client";

import { useState, useEffect, useCallback } from "react";
import NavSidebar from "@/components/ui/NavSidebar";
import TradePlanCard from "@/components/plans/TradePlanCard";
import type { TradePlanData } from "@/lib/parseTradePlan";

interface SavedPlan extends TradePlanData {
  id: string;
  status: string;
  created_at: string;
  updated_at: string;
  source_type: string;
}

const STATUS_TABS = [
  { key: "", label: "全部" },
  { key: "pending", label: "待执行" },
  { key: "executing", label: "执行中" },
  { key: "completed", label: "已完成" },
  { key: "expired", label: "已过期" },
  { key: "ignored", label: "已忽略" },
];

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function PlansPage() {
  const [plans, setPlans] = useState<SavedPlan[]>([]);
  const [activeTab, setActiveTab] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  const fetchPlans = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (activeTab) params.set("status", activeTab);
      if (search) params.set("stock_code", search);
      const resp = await fetch(`${API_BASE}/api/v1/agent/plans?${params}`);
      if (resp.ok) {
        setPlans(await resp.json());
      }
    } finally {
      setLoading(false);
    }
  }, [activeTab, search]);

  useEffect(() => {
    fetchPlans();
  }, [fetchPlans]);

  const handleStatusChange = async (id: string, status: string) => {
    await fetch(`${API_BASE}/api/v1/agent/plans/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    fetchPlans();
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确定删除这个交易计划？")) return;
    await fetch(`${API_BASE}/api/v1/agent/plans/${id}`, { method: "DELETE" });
    fetchPlans();
  };

  // 前端判断过期
  const today = new Date().toISOString().slice(0, 10);
  const displayPlans = plans.map((p) => ({
    ...p,
    status:
      p.status === "pending" && p.valid_until && p.valid_until < today
        ? "expired"
        : p.status,
  }));

  return (
    <div className="flex h-screen bg-[#0a0a0f] text-white">
      <NavSidebar />
      <div className="flex-1 flex flex-col ml-12 p-6">
        {/* 标题 */}
        <h1 className="text-xl font-bold mb-4">📋 交易计划备忘录</h1>

        {/* 筛选栏 */}
        <div className="flex items-center gap-4 mb-4">
          <div className="flex gap-1 bg-white/5 rounded-lg p-1">
            {STATUS_TABS.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`px-3 py-1.5 rounded text-sm transition-colors ${
                  activeTab === tab.key
                    ? "bg-white/15 text-white"
                    : "text-gray-400 hover:text-white"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <input
            type="text"
            placeholder="搜索股票代码..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-sm text-white placeholder-gray-500 w-48"
          />
        </div>

        {/* 计划列表 */}
        <div className="flex-1 overflow-y-auto space-y-3">
          {loading ? (
            <div className="text-gray-500 text-center py-10">加载中...</div>
          ) : displayPlans.length === 0 ? (
            <div className="text-gray-500 text-center py-10">
              暂无交易计划。在专家对话中，AI 给出的交易建议可以一键收藏到这里。
            </div>
          ) : (
            displayPlans.map((plan) => (
              <TradePlanCard
                key={plan.id}
                plan={plan}
                savedPlan={{
                  id: plan.id,
                  status: plan.status,
                  created_at: plan.created_at,
                }}
                onStatusChange={handleStatusChange}
                onDelete={handleDelete}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 在 NavSidebar 中新增 /plans 导航项**

读取 `frontend/components/ui/NavSidebar.tsx`，在导航项数组中新增：

```tsx
{ icon: "📋", label: "交易计划", href: "/plans" },
```

插入位置：在现有导航项之间，建议放在"投资专家"之后。

- [ ] **Step 3: 验证前端编译通过**

Run: `cd frontend && npm run build`
Expected: 编译成功

- [ ] **Step 4: Commit**

```bash
git add frontend/app/plans/page.tsx frontend/components/ui/NavSidebar.tsx
git commit -m "feat(plans): /plans 备忘页签 + 导航栏入口"
```

---

## 最终验证

- [ ] **Step 1: 运行全部后端测试**

Run: `python3 -m pytest tests/unit/test_trade_plans.py tests/unit/test_agent_phase1a.py -v`
Expected: 全部通过

- [ ] **Step 2: 运行前端编译**

Run: `cd frontend && npm run build`
Expected: 编译成功

- [ ] **Step 3: 最终 Commit**

```bash
git add -A
git commit -m "feat: Phase 1B-1 交易计划备忘录完整实现"
```
