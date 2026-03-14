# Claude A: LLM-RAG 基础设施 — Worktree 执行计划

> **For agentic workers:** REQUIRED: 先用 `superpowers:using-git-worktrees` 创建隔离 worktree，再用 `superpowers:executing-plans` 按本计划逐 Task 执行。Steps 使用 checkbox (`- [ ]`) 语法追踪进度。

---

## 0. 并行协作上下文

本计划是 **双 Claude 并行开发** 的 Claude A 部分：

| 角色 | 分支 | 职责 |
|------|------|------|
| **Claude A（你）** | `feature/llm-rag-infrastructure` | LLM 基础设施 + RAG + InfoEngine 重构 + Agent 层适配 |
| **Claude B（另一个会话）** | `feature/expert-debate-system` | 辩论数据模型 + 角色人格 + debate.py 核心逻辑 + MCP tools |

**合并顺序：先 A 后 B。** Claude A 的产出是 Claude B 的运行时依赖（`LLMCapability`、`fetch_by_request()`、`RAGStore`）。

### 你不碰的文件（Claude B 领地）

- `engine/agent/schemas.py` — 辩论数据模型（Blackboard / DebateEntry / DataRequest / JudgeVerdict）
- `engine/agent/personas.py` — 5 个辩论角色人格 + prompt 模板
- `engine/agent/debate.py` — 辩论核心逻辑（新建文件）
- `engine/mcpserver/tools.py` — 4 个 debate MCP tools
- `engine/mcpserver/server.py` — 注册 debate tools

### 共享文件（你先改，Claude B 后续追加）

| 文件 | 你的改动 | Claude B 后续改动 |
|------|---------|-----------------|
| `engine/data_engine/store.py` | `_init_tables()` 追加 shared schema + llm_cache + chat_history 表 + 4 个新方法 | 追加 debate_records 表 |
| `engine/agent/orchestrator.py` | 构造函数改 LLMCapability + RAG 注入 + runner 调用适配 | analyze() 末尾追加 Phase 4 辩论 |
| `engine/agent/data_fetcher.py` | 新增 `fetch_by_request()` + `ACTION_DISPATCH` | 只 import 使用，不改动 |

---

## 1. Worktree 设置

- [ ] **Step 1.1: 创建 worktree 和分支**

使用 `superpowers:using-git-worktrees` 或手动执行：

```bash
cd /Users/swannzhang/Workspace/AIProjects/A_Claude
git worktree add .claude/worktrees/llm-rag-infra -b feature/llm-rag-infrastructure
cd .claude/worktrees/llm-rag-infra
```

- [ ] **Step 1.2: 确认工作目录正确**

```bash
git branch --show-current   # 应输出 feature/llm-rag-infrastructure
ls engine/llm/              # 应看到 config.py providers.py context.py __init__.py
```

---

## 2. 执行实现计划

**详细 Spec:** `docs/superpowers/specs/2026-03-14-phase4-5-llm-rag-design.md`
**详细 Plan（含完整代码片段）:** `docs/superpowers/plans/2026-03-14-phase4-5-llm-rag.md`

按以下顺序执行原始 Plan 中的 7 个 Task。每个 Task 的详细步骤、代码片段、测试用例均在原始 Plan 中，此处只列出 Task 概要和关键注意事项。

---

### Chunk 1: LLMCapability + DuckDB 共享表

#### Task 1: DuckDB shared schema + llm_cache + chat_history

**对应原始 Plan:** Chunk 1 → Task 1（第 17-205 行）

**Files:**
- Modify: `engine/data_engine/store.py`（`_init_tables()` 追加 + 末尾追加 4 个新方法）
- Test: `engine/tests/test_llm_cache_store.py`（新建）

**要点:**
- [ ] `CREATE SCHEMA IF NOT EXISTS shared` 放在 `_init_tables()` 中
- [ ] `llm_cache` 表：`cache_key VARCHAR PRIMARY KEY`
- [ ] `chat_history` 表：用 `SEQUENCE` 实现自增 id（DuckDB 不自动自增）
- [ ] 新增方法：`get_llm_cache()` / `set_llm_cache()` / `append_chat_history()` / `get_chat_history()`
- [ ] TDD：先写失败测试，再实现，再验证通过

#### Task 2: LLMCapability 统一接口

**对应原始 Plan:** Chunk 1 → Task 2（第 206-530 行）

**Files:**
- Create: `engine/llm/capability.py`
- Test: `engine/tests/test_llm_capability.py`（新建）

**要点:**
- [ ] `LLMCapability` wrap `BaseLLMProvider`，三个语义化方法：`complete()` / `classify()` / `extract()`
- [ ] `enabled` 属性：`provider is None` 时返回 False，所有方法静默降级
- [ ] 缓存透明：内部自动 hash → 查 `llm_cache` → miss 才调 LLM
- [ ] `classify()` 降级返回 `{"label": categories[0], "score": 0.0, "reason": "llm_disabled"}`
- [ ] `extract()` 降级返回 `{}`
- [ ] TDD 流程

**Commit checkpoint:** Chunk 1 完成后提交 `feat: add LLMCapability + DuckDB shared tables`

---

### Chunk 2: RAG 模块 + config.py 扩展

#### Task 3: RAGConfig 注册到 AppConfig

**对应原始 Plan:** Chunk 2 → Task 3（第 533-573 行）

**Files:**
- Modify: `engine/config.py`

**要点:**
- [ ] 新增 `RAGConfig(BaseModel)` 类：`persist_dir` / `max_reports` / `search_top_k`
- [ ] `AppConfig` 新增 `rag: RAGConfig = RAGConfig()` 字段
- [ ] `persist_dir` 默认值与 AgentMemory 的 chromadb 目录隔离

#### Task 4: RAG 模块（schemas + store + 单例工厂）

**对应原始 Plan:** Chunk 2 → Task 4（第 574-822 行）

**Files:**
- Create: `engine/rag/__init__.py` / `engine/rag/store.py` / `engine/rag/schemas.py`
- Test: `engine/tests/test_rag_store.py`（新建）

**要点:**
- [ ] `ReportRecord` pydantic 模型：`report_id` / `code` / `summary` / `signal` / `score` / `report_type` / `created_at`
- [ ] `RAGStore`：ChromaDB `PersistentClient`，collection 名 `analysis_reports`
- [ ] `store()` 用 `upsert`，`search()` 支持 `code_filter`
- [ ] `get_rag_store()` 单例工厂
- [ ] 空 collection 检索返回 `[]`

**Commit checkpoint:** Chunk 2 完成后提交 `feat: add RAG module + RAGConfig`

---

### Chunk 3: InfoEngine 重构 + Agent 层适配

#### Task 5: InfoEngine 重构

**对应原始 Plan:** Chunk 3 → Task 5（第 825-1096 行）

**Files:**
- Modify: `engine/info_engine/sentiment.py` / `engine/info_engine/event_assessor.py` / `engine/info_engine/__init__.py`
- Modify: existing tests（更新 mock 对象）

**要点:**
- [ ] `SentimentAnalyzer.__init__` 从 `llm_provider: BaseLLMProvider` 改为 `llm_capability: LLMCapability`
- [ ] `_analyze_llm()` 改用 `self._llm.classify(text, ["positive", "negative", "neutral"])`
- [ ] `EventAssessor` 类似改用 `self._llm.extract()`
- [ ] `get_info_engine()` 工厂函数改为注入 `LLMCapability`
- [ ] `InfoEngine.__init__` 签名更新
- [ ] 现有测试只需更新 mock 对象，行为不变

#### Task 6: Agent 层适配（runner.py + data_fetcher.py + orchestrator.py）

**对应原始 Plan:** Chunk 3 → Task 6（第 1097-1437 行）

**Files:**
- Modify: `engine/agent/runner.py` / `engine/agent/data_fetcher.py` / `engine/agent/orchestrator.py`
- Test: `engine/tests/test_data_fetcher_dispatch.py`（新建）

**要点:**
- [ ] `data_fetcher.py`：新增 `ACTION_DISPATCH` 3-tuple 路由表 + `fetch_by_request()` async 方法
- [ ] `ACTION_DISPATCH` 中 `is_async` 标志区分 sync/async 方法（sync 用 `asyncio.to_thread()`）
- [ ] `runner.py`：`run_agent()` 签名从 `BaseLLMProvider` 改为 `LLMCapability`
- [ ] `orchestrator.py`：构造函数改为接受 `LLMCapability` + `rag_store`；analyze() 中注入 RAG 历史报告到 `data_map["historical_reports"]`；末尾写入 RAGStore
- [ ] **注意：** orchestrator.py 的 analyze() 末尾不要加 Phase 4 辩论代码（那是 Claude B 的工作）

#### Task 7: MCP 预留注释 + E2E 验证

**对应原始 Plan:** Chunk 3 → Task 7（第 1438 行至末尾）

**Files:**
- Modify: `engine/mcpserver/tools.py`（仅添加 TODO 注释）

**要点:**
- [ ] `tools.py` 添加 `# TODO Phase 4: full_analysis 组合工具` 预留注释
- [ ] E2E 验证：启动后端，确认 health_check 正常，LLMCapability disabled 时所有功能降级正常
- [ ] 运行全部测试确认无回归

**Commit checkpoint:** Chunk 3 完成后提交 `feat: refactor InfoEngine + adapt Agent layer to LLMCapability`

---

## 3. 完成后操作

- [ ] **Step 3.1: 运行全部测试**

```bash
cd engine && python -m pytest tests/ -v
```

- [ ] **Step 3.2: 提交所有改动**（如果中间没有逐 chunk 提交的话）

- [ ] **Step 3.3: 通知用户合并**

完成后告知用户：
> "Claude A worktree 开发完成，分支 `feature/llm-rag-infrastructure` 已就绪。请合并到 main 后通知 Claude B 继续 orchestrator Phase 4 集成。"

**合并命令参考：**
```bash
cd /Users/swannzhang/Workspace/AIProjects/A_Claude
git merge feature/llm-rag-infrastructure
git worktree remove .claude/worktrees/llm-rag-infra
```
