# 双 Claude 并行开发协调文档

> **日期:** 2026-03-14
> **目标:** 并行实现 Phase 4+5 LLM-RAG 基础设施 + Expert Debate System

---

## 总览

```
main ─────────────────────────────────────────────────────► main (最终)
  │                                                          ▲
  ├─► feature/llm-rag-infrastructure (Claude A) ──merge①──►  │
  │                                                          │
  └─► feature/expert-debate-system (Claude B) ───rebase──merge②──►
```

| 角色 | 分支 | 计划文件 | 参考 Spec |
|------|------|---------|----------|
| Claude A | `feature/llm-rag-infrastructure` | `plans/2026-03-14-claude-a-llm-rag-worktree.md` | `specs/2026-03-14-phase4-5-llm-rag-design.md` |
| Claude B | `feature/expert-debate-system` | `plans/2026-03-14-claude-b-debate-worktree.md` | `specs/2026-03-14-expert-debate-system-design.md` |

**详细实现参考（含完整代码片段）：**
- Claude A: `plans/2026-03-14-phase4-5-llm-rag.md`
- Claude B: `plans/2026-03-14-expert-debate-system.md`

---

## 依赖关系

```
Claude A 产出                    Claude B 消费
─────────────────────────────────────────────────
LLMCapability.complete()    ←──  debate.py speak()
DataFetcher.fetch_by_request() ← debate.py fulfill_data_requests()
RAGStore.store()            ←──  debate.py persist_debate()
Orchestrator(LLMCapability) ←──  orchestrator.py Phase 4 接入
DuckDB shared schema        ←──  debate_records 表（同 schema）
```

Claude B 的 Phase 1（schemas / personas / debate.py / MCP tools）可独立开发，不依赖 Claude A。
Claude B 的 Phase 2（Orchestrator 集成 / E2E 测试）必须等 Claude A 合并后执行。

---

## 文件冲突矩阵

| 文件 | Claude A | Claude B | 冲突风险 |
|------|----------|----------|---------|
| `engine/llm/capability.py` | 新建 | — | 无 |
| `engine/rag/*` | 新建 | — | 无 |
| `engine/config.py` | 修改 | — | 无 |
| `engine/info_engine/*` | 修改 | — | 无 |
| `engine/agent/schemas.py` | — | 修改 | 无 |
| `engine/agent/personas.py` | — | 修改 | 无 |
| `engine/agent/debate.py` | — | 新建 | 无 |
| `engine/mcpserver/tools.py` | 预留注释 | 新增 4 tools | 低 |
| `engine/mcpserver/server.py` | — | 注册 tools | 无 |
| `engine/data_engine/store.py` | 追加 shared + llm_cache + chat_history | 追加 debate_records | 中（同位置追加） |
| `engine/agent/data_fetcher.py` | 新增 fetch_by_request | — | 无 |
| `engine/agent/runner.py` | LLMCapability 适配 | — | 无 |
| `engine/agent/orchestrator.py` | 构造函数 + RAG 注入 | Phase 4 追加 | 中（不同位置） |

**冲突解决策略：** 合并 Claude B 时，`store.py` 和 `orchestrator.py` 可能有冲突。两者改动位置不同（A 改构造函数/初始化，B 改 analyze() 末尾），手动合并即可。

---

## 合并步骤

### Step 1: 合并 Claude A

```bash
cd /Users/swannzhang/Workspace/AIProjects/A_Claude
git merge feature/llm-rag-infrastructure
# 运行测试确认
cd engine && python -m pytest tests/ -v
```

### Step 2: Rebase Claude B

```bash
cd .claude/worktrees/debate-system
git rebase main
# 解决可能的 store.py 冲突（追加 debate_records 表到 _init_tables 末尾）
```

### Step 3: Claude B Phase 2 集成

在 rebase 后的 worktree 中执行 Claude B 计划的 Phase 2：
- Task 6: Orchestrator Phase 4 接入
- Task 7: E2E 冒烟测试
- Task 8: 清理临时代码

### Step 4: 合并 Claude B

```bash
cd /Users/swannzhang/Workspace/AIProjects/A_Claude
git merge feature/expert-debate-system
cd engine && python -m pytest tests/ -v
```

### Step 5: 清理

```bash
git worktree remove .claude/worktrees/llm-rag-infra 2>/dev/null
git worktree remove .claude/worktrees/debate-system 2>/dev/null
git branch -d feature/llm-rag-infrastructure feature/expert-debate-system
```

---

## 启动指令

### 给 Claude A 的指令（复制到另一个 Claude Code 终端）

```
请阅读 docs/superpowers/plans/2026-03-14-claude-a-llm-rag-worktree.md，
这是你的执行计划。使用 superpowers:using-git-worktrees 创建 worktree，
然后用 superpowers:executing-plans 按计划执行。
详细代码参考 docs/superpowers/plans/2026-03-14-phase4-5-llm-rag.md。
```

### Claude B（当前会话）

```
阅读 docs/superpowers/plans/2026-03-14-claude-b-debate-worktree.md，
创建 worktree 后执行 Phase 1 部分。
详细代码参考 docs/superpowers/plans/2026-03-14-expert-debate-system.md。
```
