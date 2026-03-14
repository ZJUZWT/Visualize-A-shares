# Claude B: Expert Debate System — Worktree 执行计划

> **For agentic workers:** REQUIRED: 先用 `superpowers:using-git-worktrees` 创建隔离 worktree，再用 `superpowers:executing-plans` 按本计划逐 Task 执行。Steps 使用 checkbox (`- [ ]`) 语法追踪进度。

---

## 0. 并行协作上下文

本计划是 **双 Claude 并行开发** 的 Claude B 部分：

| 角色 | 分支 | 职责 |
|------|------|------|
| **Claude A（另一个会话）** | `feature/llm-rag-infrastructure` | LLM 基础设施 + RAG + InfoEngine 重构 + Agent 层适配 |
| **Claude B（你）** | `feature/expert-debate-system` | 辩论数据模型 + 角色人格 + debate.py 核心逻辑 + MCP tools |

**合并顺序：先 A 后 B。** Claude A 提供的 `LLMCapability`、`fetch_by_request()`、`RAGStore` 是你的运行时依赖。

### 你的独占文件

- `engine/agent/schemas.py` — 新增 4 个辩论数据模型
- `engine/agent/personas.py` — 新增 5 个辩论角色人格
- `engine/agent/debate.py` — 新建，辩论核心逻辑
- `engine/mcpserver/tools.py` — 新增 4 个 debate MCP tools
- `engine/mcpserver/server.py` — 注册 debate tools

### 跳过的 Task（Claude A 负责）

原始 Plan 中的 **Chunk 2 Task 3（DataFetcher 路由扩展）** 由 Claude A 实现。你的 `debate.py` 中 `fulfill_data_requests()` 直接 import `DataFetcher.fetch_by_request()` 使用即可。

### 延迟的 Task（等 Claude A 合并后执行）

| 原始 Plan Task | 原因 | 何时执行 |
|---------------|------|---------|
| Task 5: Orchestrator 接入 Phase 4 | 依赖 Claude A 对 orchestrator.py 的 LLMCapability 改造 | Claude A 合并到 main 后 |
| Task 7: 端到端冒烟测试 | 依赖完整集成 | 合并后 |
| Task 8: 最终验证和清理 | 依赖完整集成 | 合并后 |

### 共享文件（Claude A 先改，你后续追加）

| 文件 | Claude A 的改动 | 你的后续改动 |
|------|---------------|------------|
| `engine/data_engine/store.py` | shared schema + llm_cache + chat_history | 追加 debate_records 表 |
| `engine/agent/orchestrator.py` | 构造函数 LLMCapability 适配 | analyze() 末尾追加 Phase 4 辩论调用 |

---

## 1. Worktree 设置

- [ ] **Step 1.1: 创建 worktree 和分支**

使用 `superpowers:using-git-worktrees` 或手动执行：

```bash
cd /Users/swannzhang/Workspace/AIProjects/A_Claude
git worktree add .claude/worktrees/debate-system -b feature/expert-debate-system
cd .claude/worktrees/debate-system
```

- [ ] **Step 1.2: 确认工作目录正确**

```bash
git branch --show-current   # 应输出 feature/expert-debate-system
ls engine/agent/            # 应看到 orchestrator.py schemas.py personas.py 等
```

---

## 2. 执行实现计划（Phase 1: 独立开发部分）

**详细 Spec:** `docs/superpowers/specs/2026-03-14-expert-debate-system-design.md`
**详细 Plan（含完整代码片段）:** `docs/superpowers/plans/2026-03-14-expert-debate-system.md`

Phase 1 执行原始 Plan 中可独立完成的 Task（不依赖 Claude A 产出）。

---

### Chunk 1: 数据结构（schemas + personas）

#### Task 1: 新增辩论数据模型到 schemas.py

**对应原始 Plan:** Chunk 1 → Task 1（第 32-246 行）

**Files:**
- Modify: `engine/agent/schemas.py`
- Test: `tests/agent/test_debate_schemas.py`（新建）

**要点:**
- [ ] 新增 4 个 Pydantic v2 模型：`Blackboard` / `DebateEntry` / `DataRequest` / `JudgeVerdict`
- [ ] `Blackboard.status` 使用 `Literal["debating", "final_round", "judging", "completed"]`
- [ ] `DebateEntry.stance` 使用 `Literal["insist", "partial_concede", "concede"] | None`
- [ ] `JudgeVerdict.debate_quality` 使用 `Literal["consensus", "strong_disagreement", "one_sided"]`
- [ ] `DEBATE_DATA_WHITELIST` 和 `MAX_DATA_REQUESTS_PER_ROLE_PER_ROUND` 常量定义在 schemas.py 或独立常量文件
- [ ] TDD：先写失败测试，再实现

#### Task 2: 新增辩论角色人格到 personas.py

**对应原始 Plan:** Chunk 1 → Task 2（第 247-421 行）

**要点:**
- [ ] 在现有 `AGENT_PERSONAS` dict 中追加 5 个辩论角色：`bull_expert` / `bear_expert` / `retail_investor` / `smart_money` / `judge`
- [ ] 每个角色包含完整 system prompt（参考 Spec Section 5）
- [ ] 辩论者（bull/bear）prompt 包含 JSON 输出格式说明
- [ ] 观察员（retail/smart_money）prompt 包含 speak 决策说明
- [ ] 裁判 prompt 包含 debate_quality 判定规则

**Commit checkpoint:** `feat: add debate schemas and personas`

---

### Chunk 2: 辩论核心逻辑 ← 跳过原始 Plan 的 Chunk 2（DataFetcher），直接进入 Chunk 3

#### Task 3: 新建 debate.py — 核心辩论逻辑

**对应原始 Plan:** Chunk 3 → Task 4（第 551-1139 行）

**Files:**
- Create: `engine/agent/debate.py`
- Test: `tests/agent/test_debate_core.py`（新建）

**要点:**
- [ ] `run_debate()` async generator：驱动辩论主循环，yield SSE 事件
- [ ] `speak()` 函数：构建 prompt → 调 LLM → 解析 DebateEntry → 错误处理 fallback
- [ ] `judge_summarize()`：读完整 Blackboard → 调 LLM → 解析 JudgeVerdict → 注入 target/debate_id/termination_reason/timestamp
- [ ] `fulfill_data_requests()`：遍历 pending DataRequest，调用 `DataFetcher.fetch_by_request()`
- [ ] `validate_data_requests()`：白名单过滤 + 数量截断
- [ ] `persist_debate()`：写 DuckDB `shared.debate_records` + `shared.analysis_reports`
- [ ] `_fallback_entry()`：LLM 超时/失败时的默认发言
- [ ] `build_debate_prompt()`：根据角色 + Blackboard 状态 + memory 构建 messages
- [ ] `parse_debate_entry()`：解析 LLM JSON 输出为 DebateEntry

**LLM 调用临时方案：** 在 Claude A 合并前，`speak()` 暂时直接使用 `BaseLLMProvider.chat(messages)`。合并后改为 `LLMCapability.complete(prompt, system)`。在代码中用注释标记：

```python
# TODO: 合并 Claude A 后改为 LLMCapability.complete()
raw = await asyncio.wait_for(llm.chat(messages), timeout=45.0)
```

**DataFetcher 临时方案：** `fulfill_data_requests()` 中对 `fetch_by_request` 的调用，在 Claude A 合并前可以先写成：

```python
# TODO: 合并 Claude A 后 DataFetcher 已有 fetch_by_request()
# 临时实现：直接按 action 手动路由
async def _temp_fetch(req: DataRequest) -> Any:
    """临时路由，合并后删除"""
    raise NotImplementedError(f"等待 Claude A 提供 fetch_by_request: {req.action}")
```

**Commit checkpoint:** `feat: add debate.py core logic`

---

### Chunk 3: DuckDB debate_records 表

#### Task 4: 新增 debate_records 表到 store.py

**Files:**
- Modify: `engine/data_engine/store.py`

**要点:**
- [ ] 在 `_init_tables()` 末尾追加（在 Claude A 添加的 shared schema 之后）：

```sql
CREATE TABLE IF NOT EXISTS shared.debate_records (
    id                  VARCHAR PRIMARY KEY,
    target              VARCHAR,
    max_rounds          INTEGER,
    rounds_completed    INTEGER,
    termination_reason  VARCHAR,
    blackboard_json     TEXT,
    judge_verdict_json  TEXT,
    created_at          TIMESTAMP,
    completed_at        TIMESTAMP
);
```

- [ ] 新增方法：`save_debate_record()` / `get_debate_record()` / `list_debate_records()`

**注意：** 此 Task 修改 `store.py`，与 Claude A 的改动在同一文件但不同位置（都是在 `_init_tables()` 末尾追加）。合并时可能需要手动解决冲突，但改动是纯 additive 的。

**Commit checkpoint:** `feat: add debate_records DuckDB table`

---

### Chunk 4: MCP Debate Tools

#### Task 5: 新增 4 个 MCP Debate Tools

**对应原始 Plan:** Chunk 4 → Task 6（第 1195-1401 行）

**Files:**
- Modify: `engine/mcpserver/tools.py`
- Modify: `engine/mcpserver/server.py`

**要点:**
- [ ] `start_debate(code: str, max_rounds: int = 3)` — 发起辩论，返回 debate_id
- [ ] `get_debate_status(debate_id: str)` — 查询辩论进度
- [ ] `get_debate_transcript(debate_id: str, round: int = None, role: str = None)` — 获取辩论记录
- [ ] `get_judge_verdict(debate_id: str)` — 获取裁判总结
- [ ] 在 `server.py` 中注册 4 个新 tool
- [ ] `start_debate` 内部需要初始化 Blackboard 并调用 `run_debate()`，但由于 Orchestrator 集成尚未完成，可以先实现为独立调用

**Commit checkpoint:** `feat: add 4 debate MCP tools`

---

## 3. Phase 2: 集成部分（等 Claude A 合并后执行）

> **触发条件：** Claude A 的 `feature/llm-rag-infrastructure` 已合并到 main。
> 执行前先 rebase：`git rebase main`

### Task 6: Orchestrator 接入 Phase 4

**对应原始 Plan:** Chunk 4 → Task 5（第 1142-1194 行）

**Files:**
- Modify: `engine/agent/orchestrator.py`

**要点:**
- [ ] 在 `analyze()` 的聚合阶段之后、返回结果之前，追加 Phase 4 辩论：

```python
# ── Phase 4: 专家辩论 ──
blackboard = Blackboard(
    target=target,
    debate_id=f"{target}_{datetime.now(tz=ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d%H%M%S')}",
    facts=data_map,
    worker_verdicts=verdicts,
    conflicts=report.conflicts,
)
async for event in run_debate(blackboard, self._llm, self._memory, self._data):
    yield event
```

- [ ] 将 `speak()` 中的 `llm.chat(messages)` 改为 `LLMCapability.complete(prompt, system)`
- [ ] 将 `fulfill_data_requests()` 中的临时路由替换为 `DataFetcher.fetch_by_request()`
- [ ] 将 `persist_debate()` 中添加 `get_rag_store().store()` 写入 JudgeVerdict

### Task 7: 端到端冒烟测试

**对应原始 Plan:** Chunk 5 → Task 7（第 1404-1609 行）

- [ ] Mock LLM provider，验证完整 analyze() 流程包含辩论阶段
- [ ] 验证 SSE 事件序列：`debate_start` → `debate_round_start` → `debate_entry` × N → `debate_end` → `judge_verdict`
- [ ] 验证 DuckDB `shared.debate_records` 写入
- [ ] 验证 ChromaDB 5 个新 collection 自动创建

### Task 8: 最终验证和清理

**对应原始 Plan:** Chunk 5 → Task 8（第 1610 行至末尾）

- [ ] 删除所有 `# TODO: 合并 Claude A 后...` 临时注释
- [ ] 删除 `_temp_fetch()` 临时实现
- [ ] 运行全部测试：`cd engine && python -m pytest tests/ -v`
- [ ] 确认无回归

**Final commit:** `feat: integrate debate system with LLM-RAG infrastructure`

---

## 4. 完成后操作

- [ ] **Step 4.1: 合并到 main**

```bash
cd /Users/swannzhang/Workspace/AIProjects/A_Claude
git merge feature/expert-debate-system
```

- [ ] **Step 4.2: 清理 worktree**

```bash
git worktree remove .claude/worktrees/debate-system
git branch -d feature/expert-debate-system
```

- [ ] **Step 4.3: 最终全量测试**

```bash
cd engine && python -m pytest tests/ -v
```
