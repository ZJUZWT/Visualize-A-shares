# 禁止数据截断 + 全链路耗时统计 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 移除所有违规的原始数据截断，并为全链路关键调用添加耗时统计

**Architecture:** 分两个 Chunk 执行：(1) 移除 10 处违规截断，用完整数据替代 (2) 新增耗时统计中间件和各层计时。截断修复优先级高于耗时统计。

**Tech Stack:** Python, FastAPI, Loguru, time.monotonic()

---

## Chunk 1: 移除违规数据截断

### Task 1: 移除专家对话历史截断

**Files:**
- Modify: `backend/engine/expert/agent.py` (第 396-397 行, 第 861-862 行)
- Modify: `backend/engine/expert/engine_experts.py` (第 585-586 行)

- [x] **Step 1: 修复 agent.py `_think` 方法中的对话历史截断**

在 `agent.py` 约第 396 行，找到：
```python
content = content[:500] + "..."
```
替换为完整内容传递（移除截断）：
```python
# 不截断 — 保持原始数据完整性
```
即删除这行截断代码，让 `content` 保持原值。

- [x] **Step 2: 修复 agent.py 综合回复中的对话历史截断**

在 `agent.py` 约第 861 行，找到：
```python
content = content[:800] + "..."
```
同样删除截断，保持 content 原值。

- [x] **Step 3: 修复 engine_experts.py 中的对话历史截断**

在 `engine_experts.py` 约第 585 行，找到：
```python
content = content[:500] + "..."
```
删除截断。

- [x] **Step 4: 验证专家对话功能正常**

```bash
cd backend && .venv/bin/python -c "
from engine.expert.agent import ExpertAgent
print('ExpertAgent import OK')
"
```
Expected: OK

- [x] **Step 5: Commit**

```bash
git add backend/engine/expert/agent.py backend/engine/expert/engine_experts.py
git commit -m "fix: 移除专家对话历史截断，保持原始数据完整性"
```

---

### Task 2: 移除辩论裁判截断

**Files:**
- Modify: `backend/engine/arena/judge.py` (第 36-37, 71, 189-191, 212 行)

- [x] **Step 1: 修复 `_build_verdict_query` 中的论点截断**

在 `judge.py` 约第 36-37 行，找到：
```python
bull_summary = bull_entries[-1].argument[:300] if bull_entries else ""
bear_summary = bear_entries[-1].argument[:300] if bear_entries else ""
```
替换为完整传递：
```python
bull_summary = bull_entries[-1].argument if bull_entries else ""
bear_summary = bear_entries[-1].argument if bear_entries else ""
```

- [x] **Step 2: 修复 `_parse_briefing` fallback 中的截断**

在 `judge.py` 约第 71 行，找到：
```python
"summary": reply[:500] if reply else "预分析完成"
```
替换为：
```python
"summary": reply if reply else "预分析完成"
```

- [x] **Step 3: 修复 `round_eval` 中的图谱召回查询截断**

在 `judge.py` 约第 189-191 行，找到：
```python
bull_arg = bull_entry.argument[:250] if bull_entry else ""
bear_arg = bear_entry.argument[:250] if bear_entry else ""
recall_query = f"{bull_arg} {bear_arg}".strip()[:500]
```
替换为：
```python
bull_arg = bull_entry.argument if bull_entry else ""
bear_arg = bear_entry.argument if bear_entry else ""
recall_query = f"{bull_arg} {bear_arg}".strip()
```

- [x] **Step 4: 修复 `round_eval` 中的数据请求结果截断**

在 `judge.py` 约第 212 行，找到：
```python
data_text = "\n".join(f"- {r.action}: {str(r.result)[:200]}" for r in done_data)
```
替换为：
```python
data_text = "\n".join(f"- {r.action}: {str(r.result)}" for r in done_data)
```

- [x] **Step 5: Commit**

```bash
git add backend/engine/arena/judge.py
git commit -m "fix: 移除辩论裁判中的论点/数据截断"
```

---

### Task 3: 移除辩论上下文和专家工具截断

**Files:**
- Modify: `backend/engine/arena/debate.py` (第 800 行)
- Modify: `backend/engine/expert/tools.py` (第 52 行)
- Modify: `backend/engine/expert/personas.py` (第 99 行)

- [x] **Step 1: 修复 debate.py 新闻内容截断**

在 `debate.py` 约第 800 行，找到：
```python
parts.append(f"  [{item.get('sentiment','')}] {item.get('title','')} — {str(item.get('content',''))[:200]}")
```
替换为：
```python
parts.append(f"  [{item.get('sentiment','')}] {item.get('title','')} — {str(item.get('content',''))}")
```

注意：同一区域可能有类似的截断（约第 803 行），检查并一并修复。

- [x] **Step 2: 修复 tools.py 工具调用结果截断**

在 `tools.py` 约第 52 行，找到：
```python
return summary[:500]
```
替换为：
```python
return summary
```

- [x] **Step 3: 修复 personas.py 记忆内容截断**

在 `personas.py` 约第 99 行，找到：
```python
return "\n".join(f"- {m['content'][:200]}" for m in memories[:3])
```
替换为（移除内容截断，但保留条目数限制 — 这是列表切片不是字符串截断）：
```python
return "\n".join(f"- {m['content']}" for m in memories[:5])
```
将条目数从 3 扩大到 5，并移除内容截断。

- [x] **Step 4: 验证所有修改可导入**

```bash
cd backend && .venv/bin/python -c "
from engine.arena.debate import run_debate
from engine.expert.tools import ExpertTools
from engine.expert.personas import format_memory_context
print('All OK')
"
```
Expected: All OK

- [x] **Step 5: Commit**

```bash
git add backend/engine/arena/debate.py backend/engine/expert/tools.py backend/engine/expert/personas.py
git commit -m "fix: 移除辩论上下文/工具结果/记忆的数据截断"
```

---

## Chunk 2: 全链路耗时统计

### Task 4: 新增 FastAPI 请求耗时中间件

**Files:**
- Modify: `backend/main.py`

- [x] **Step 1: 在 main.py 中添加请求耗时中间件**

在 `CORSMiddleware` 之后添加自定义中间件：

```python
import time

@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    elapsed = time.monotonic() - start
    path = request.url.path
    method = request.method
    status = response.status_code
    # 跳过健康检查等高频低价值路由
    if path not in ("/api/v1/health",):
        logger.info(f"⏱️ {method} {path} → {status} 耗时 {elapsed:.2f}s")
    if elapsed > 5.0:
        logger.warning(f"🐢 慢请求: {method} {path} 耗时 {elapsed:.1f}s")
    response.headers["X-Response-Time"] = f"{elapsed:.3f}s"
    return response
```

- [x] **Step 2: 验证中间件生效**

```bash
cd backend && .venv/bin/python -c "import main; print('OK')"
```
Expected: OK

- [x] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: 新增 FastAPI 请求耗时中间件"
```

---

### Task 5: LLM Provider 层耗时统计

**Files:**
- Modify: `backend/llm/providers.py`

- [x] **Step 1: 为 `chat()` 添加耗时统计**

在 `OpenAICompatibleProvider.chat()` 和 `AnthropicProvider.chat()` 中添加计时：

```python
import time

# 在方法开头
t0 = time.monotonic()

# 在方法 return 之前
elapsed = time.monotonic() - t0
logger.info(f"⏱️ LLM chat ({self.model}) 耗时 {elapsed:.1f}s, 响应长度 {len(result)} 字符")
```

- [x] **Step 2: 为 `chat_stream()` 添加耗时统计**

在 `chat_stream()` 方法中添加：

```python
t0 = time.monotonic()
token_count = 0

# 在每个 yield token 处
token_count += 1

# 在方法最后（finally 块或 generator 结束后）
elapsed = time.monotonic() - t0
logger.info(f"⏱️ LLM stream ({self.model}) 耗时 {elapsed:.1f}s, {token_count} tokens")
```

注意：`chat_stream()` 是 `async generator`，需要用 try/finally 确保在生成器结束时输出日志。

- [x] **Step 3: Commit**

```bash
git add backend/llm/providers.py
git commit -m "feat: LLM Provider 层 chat/chat_stream 耗时统计"
```

---

### Task 6: 辩论引擎耗时统计

**Files:**
- Modify: `backend/engine/arena/debate.py`

- [x] **Step 1: 添加 `run_debate()` 总耗时和每轮耗时**

在 `run_debate()` 入口添加 `t0_debate = time.monotonic()`，每轮开始添加 `t0_round = time.monotonic()`。

每轮结束后：
```python
round_elapsed = time.monotonic() - t0_round
logger.info(f"⏱️ 辩论第 {round_num} 轮 耗时 {round_elapsed:.1f}s")
yield sse("timing", {"round": round_num, "elapsed_s": round(round_elapsed, 1)})
```

辩论结束后：
```python
total_elapsed = time.monotonic() - t0_debate
logger.info(f"⏱️ 辩论总耗时 {total_elapsed:.1f}s ({round_count} 轮)")
yield sse("timing", {"total_elapsed_s": round(total_elapsed, 1), "rounds": round_count})
```

- [x] **Step 2: 添加每个角色发言耗时**

在 `speak_stream()` / `speak()` 调用前后添加计时：
```python
t0_speak = time.monotonic()
# ... speak 调用 ...
speak_elapsed = time.monotonic() - t0_speak
logger.info(f"⏱️ {role} 发言 耗时 {speak_elapsed:.1f}s")
```

- [x] **Step 3: Commit**

```bash
git add backend/engine/arena/debate.py
git commit -m "feat: 辩论引擎 run_debate 总耗时/每轮/发言耗时统计"
```

---

### Task 7: 专家对话和数据引擎耗时统计

**Files:**
- Modify: `backend/engine/expert/agent.py`
- Modify: `backend/engine/arena/data_fetcher.py`
- Modify: `backend/engine/info/engine.py`
- Modify: `backend/engine/industry/engine.py`

- [x] **Step 1: expert/agent.py — 专家对话总耗时**

在 `chat()` / `recall_and_think()` 方法入口添加 `t0 = time.monotonic()`，结束时输出耗时日志。

- [x] **Step 2: data_fetcher.py — 每个 action 耗时**

在 `fetch_by_request()` 中为每个 dispatch action 添加计时：
```python
t0 = time.monotonic()
result = await method(...)
elapsed = time.monotonic() - t0
logger.info(f"⏱️ DataFetcher.{action} 耗时 {elapsed:.1f}s")
```

- [x] **Step 3: info/engine.py — 新闻/公告获取耗时**

为 `get_news()`、`get_announcements()`、`assess_event_impact()` 添加计时。

- [x] **Step 4: industry/engine.py — 行业认知生成耗时**

为 `analyze()`、`get_capital_structure()` 添加计时。

- [x] **Step 5: Commit**

```bash
git add backend/engine/expert/agent.py backend/engine/arena/data_fetcher.py backend/engine/info/engine.py backend/engine/industry/engine.py
git commit -m "feat: 专家/DataFetcher/信息/行业引擎 耗时统计"
```

---

### Task 8: 运行测试验证无回归

- [x] **Step 1: 运行全量测试**

```bash
cd /Users/swannzhang/Workspace/AIProjects/A_Claude/Visualize-A-shares
backend/.venv/bin/python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```
Expected: 不引入新的测试失败（允许预先存在的失败）

- [x] **Step 2: 验证后端可正常启动**

```bash
cd backend && .venv/bin/python -c "import main; print('OK')"
```

- [x] **Step 3: Commit 所有改动**

```bash
git add -A
git commit -m "feat: 禁止数据截断 + 全链路耗时统计 完成"
```
