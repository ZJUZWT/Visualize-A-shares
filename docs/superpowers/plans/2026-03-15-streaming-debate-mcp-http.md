# 流式辩论 + MCP Streamable HTTP Transport 实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 辩论系统改为逐 token 流式输出，MCP server 从 stdio 迁移到 Streamable HTTP transport，支持实时推送中间结果。

**Architecture:** 辩论 `speak()` 改为 async generator `speak_stream()`，LLM 输出纯自然语言后用轻量调用提取结构化字段。MCP server 用 FastMCP 内置 `run(transport="streamable-http")` 跑在独立端口 8001，通过 `ctx.log()` 推送 notification。

**Tech Stack:** Python 3.11, FastAPI, FastMCP (mcp>=1.26.0), httpx, asyncio, pytest

**Spec:** `docs/superpowers/specs/2026-03-15-streaming-debate-mcp-http.md`

---

## 文件结构

| 文件 | 职责 | 操作 |
|------|------|------|
| `engine/llm/providers.py:186` | Bug 修复: `_get_base_url` | 修改 |
| `engine/agent/debate.py` | `speak_stream()`, `extract_structure()`, `judge_summarize_stream()`, `sse()` 提升, 数据请求事件化 | 重构 |
| `engine/agent/personas.py:144-201` | 移除 JSON 格式要求，改为纯自然语言输出 | 修改 |
| `engine/mcpserver/__main__.py` | stdio → streamable-http | 重构 |
| `engine/mcpserver/server.py:174-177` | `start_debate` 改 async + ctx | 修改 |
| `engine/mcpserver/tools.py:1161-1306` | 新增 `start_debate_async()` | 重构 |
| `engine/api/routes/debate.py` | SSE 事件类型适配 | 修改 |
| `engine/pyproject.toml` | `mcp>=1.26.0` | 修改 |
| `.mcp.json` | stockterrain → HTTP url | 修改 |
| `engine/tests/agent/test_debate_stream.py` | 流式 speak + 提取 + judge 测试 | 新建 |
| `engine/tests/agent/test_debate_e2e.py` | 适配新事件类型 | 修改 |
| `engine/tests/mcpserver/test_http_transport.py` | MCP HTTP transport 测试 | 新建 |

---

## Chunk 1: 前置修复 + 辩论流式核心

### Task 1: 修复 AnthropicProvider.chat_stream() bug

**Files:**
- Modify: `engine/llm/providers.py:186`
- Test: `engine/tests/llm/test_providers.py` (如存在) 或内联验证

- [ ] **Step 1: 写失败测试**

```python
# engine/tests/llm/test_chat_stream_bug.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from llm.providers import AnthropicProvider, LLMConfig

@pytest.mark.asyncio
async def test_anthropic_chat_stream_url_construction():
    """验证 chat_stream 使用正确的 base_url 而非不存在的 _get_base_url()"""
    config = LLMConfig(
        provider="anthropic",
        api_key="test-key",
        base_url="https://api.example.com",
        model="claude-3",
    )
    provider = AnthropicProvider(config)

    # 应该不抛 AttributeError
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.aiter_lines = AsyncMock(return_value=iter([
            'data: {"type":"content_block_delta","delta":{"text":"hello"}}',
            'data: {"type":"message_stop"}',
        ]))
        mock_client.stream = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_resp),
            __aexit__=AsyncMock(return_value=False),
        ))

        tokens = []
        async for token in provider.chat_stream([{"role": "user", "content": "hi"}]):
            tokens.append(token)

        # 验证 URL 使用了 config.base_url
        call_args = mock_client.stream.call_args
        assert "https://api.example.com/v1/messages" in str(call_args)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd engine && python -m pytest tests/llm/test_chat_stream_bug.py -v
```
预期: FAIL (AttributeError: 'AnthropicProvider' object has no attribute '_get_base_url')

- [ ] **Step 3: 修复 bug**

`engine/llm/providers.py` 第 186 行:
```python
# 修改前
url = f"{self._get_base_url()}/v1/messages"
# 修改后
url = f"{self.config.base_url.rstrip('/')}/v1/messages"
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd engine && python -m pytest tests/llm/test_chat_stream_bug.py -v
```
预期: PASS

- [ ] **Step 5: 提交**

```bash
git add engine/llm/providers.py engine/tests/llm/test_chat_stream_bug.py
git commit -m "fix: AnthropicProvider.chat_stream() 修复不存在的 _get_base_url 调用"
```

---
### Task 2: 提升 sse() 为模块级函数 + personas prompt 改造

**Files:**
- Modify: `engine/agent/debate.py:338-339` (sse 提升)
- Modify: `engine/agent/personas.py:144-201` (移除 JSON 格式要求)

- [ ] **Step 1: 提升 sse() 到模块级**

`engine/agent/debate.py` — 在文件顶部（import 区域之后，约第 20 行）添加:
```python
def sse(event: str, data: dict) -> dict:
    """统一 SSE 事件格式"""
    return {"event": event, "data": data}
```

删除 `run_debate()` 内部第 338-339 行的同名局部函数。

- [ ] **Step 2: 改造辩论者 prompt（personas.py）**

`engine/agent/personas.py` 第 144-153 行，辩论者的 JSON 输出格式要求替换为:
```python
请直接阐述你的观点和论据，使用自然语言，不要包裹在 JSON 中。
要求：
1. 开头明确你的立场（坚持/部分让步/认输）
2. 详细展开你的核心论点，用数据和逻辑支撑
3. 在论述末尾，用"【质疑】"标记对对方的质疑（每条一行）
4. 如需补充数据，用"【数据请求】"标记（每条一行，格式：引擎.动作(参数)）
```

观察员 prompt（第 162-163 行）同样改为自然语言输出。

裁判 prompt（第 188-201 行）保持 JSON 格式不变——裁判不需要流式输出正文，结构化裁决更重要。

- [ ] **Step 3: 运行现有测试确认不破坏**

```bash
cd engine && python -m pytest tests/ -x -q
```
预期: 全部通过（prompt 改动不影响现有 mock 测试）

- [ ] **Step 4: 提交**

```bash
git add engine/agent/debate.py engine/agent/personas.py
git commit -m "refactor: sse() 提升为模块级 + 辩论 prompt 改为自然语言输出"
```

---

### Task 3: 实现 extract_structure()

**Files:**
- Modify: `engine/agent/debate.py` (新增函数)
- Create: `engine/tests/agent/test_debate_stream.py`

- [ ] **Step 1: 写失败测试**

```python
# engine/tests/agent/test_debate_stream.py
import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from agent.schemas import Blackboard, DataRequest

@pytest.mark.asyncio
async def test_extract_structure_success():
    """正常提取结构化字段"""
    from agent.debate import extract_structure

    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(return_value=json.dumps({
        "stance": "insist",
        "confidence": 0.78,
        "challenges": ["质疑1", "质疑2"],
        "data_requests": [{"engine": "quant", "action": "get_factor_scores", "params": {"code": "600406"}}],
        "retail_sentiment_score": None,
        "speak": True,
    }))

    bb = Blackboard(target="600406", debate_id="test", max_rounds=2)
    bb.round = 1

    result = await extract_structure("这是一段论点...", "bull_expert", bb, mock_llm)

    assert result["stance"] == "insist"
    assert result["confidence"] == 0.78
    assert len(result["challenges"]) == 2
    assert len(result["data_requests"]) == 1
    assert result["data_requests"][0].engine == "quant"
    assert result["speak"] is True


@pytest.mark.asyncio
async def test_extract_structure_fallback_on_timeout():
    """LLM 超时时返回 fallback 默认值"""
    import asyncio
    from agent.debate import extract_structure

    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(side_effect=asyncio.TimeoutError())

    bb = Blackboard(target="600406", debate_id="test", max_rounds=2)
    bb.round = 1

    result = await extract_structure("论点...", "bull_expert", bb, mock_llm)

    assert result["stance"] == "insist"
    assert result["confidence"] == 0.5
    assert result["challenges"] == []
    assert result["data_requests"] == []
    assert result["speak"] is True


@pytest.mark.asyncio
async def test_extract_structure_fallback_on_invalid_json():
    """LLM 返回无效 JSON 时返回 fallback"""
    from agent.debate import extract_structure

    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(return_value="这不是JSON")

    bb = Blackboard(target="600406", debate_id="test", max_rounds=2)
    bb.round = 1

    result = await extract_structure("论点...", "bull_expert", bb, mock_llm)

    assert result["stance"] == "insist"
    assert result["confidence"] == 0.5
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd engine && python -m pytest tests/agent/test_debate_stream.py -v
```
预期: FAIL (ImportError: cannot import name 'extract_structure')

- [ ] **Step 3: 实现 extract_structure()**

在 `engine/agent/debate.py` 中，`speak()` 函数之前（约第 155 行）添加:

```python
async def extract_structure(
    argument: str,
    role: str,
    blackboard: Blackboard,
    llm: BaseLLMProvider,
) -> dict:
    """从 argument 正文提取结构化字段。返回可直接解包到 DebateEntry 的 dict。"""
    extract_prompt = f"""请从以下辩论发言中提取结构化信息，只返回 JSON，不要其他内容。

角色: {role}
发言内容:
{argument}

返回格式:
{{
  "stance": "insist" | "partial_concede" | "concede",
  "confidence": 0.0-1.0,
  "challenges": ["对对方的质疑1", "质疑2", ...],
  "data_requests": [{{"engine": "quant|data|info", "action": "动作名", "params": {{...}}}}],
  "retail_sentiment_score": -1.0到1.0（仅 retail_investor 需要，其他返回 null）,
  "speak": true 或 false（observer 可选择沉默，debater 始终 true）
}}"""

    try:
        raw = await asyncio.wait_for(
            llm.chat([ChatMessage(role="user", content=extract_prompt)]),
            timeout=10.0,
        )
        json_str = _extract_json(raw)
        parsed = json.loads(json_str)
        return {
            "stance": parsed.get("stance", "insist"),
            "confidence": float(parsed.get("confidence", 0.5)),
            "challenges": parsed.get("challenges", []),
            "data_requests": [
                DataRequest(
                    requested_by=role, round=blackboard.round,
                    status="pending", engine=dr.get("engine", ""),
                    action=dr.get("action", ""), params=dr.get("params", {}),
                )
                for dr in parsed.get("data_requests", [])
            ],
            "retail_sentiment_score": parsed.get("retail_sentiment_score"),
            "speak": parsed.get("speak", True),
        }
    except Exception:
        return {
            "stance": "insist", "confidence": 0.5,
            "challenges": [], "data_requests": [],
            "retail_sentiment_score": None, "speak": True,
        }
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd engine && python -m pytest tests/agent/test_debate_stream.py -v
```
预期: 3 PASSED

- [ ] **Step 5: 提交**

```bash
git add engine/agent/debate.py engine/tests/agent/test_debate_stream.py
git commit -m "feat: 新增 extract_structure() 从自然语言论点提取结构化字段"
```

---

### Task 4: 实现 speak_stream()

**Files:**
- Modify: `engine/agent/debate.py` (新增 speak_stream)
- Modify: `engine/tests/agent/test_debate_stream.py` (新增测试)

- [ ] **Step 1: 写失败测试**

在 `engine/tests/agent/test_debate_stream.py` 追加:

```python
@pytest.mark.asyncio
async def test_speak_stream_yields_tokens_then_complete():
    """speak_stream 先 yield debate_token 事件，最后 yield debate_entry_complete"""
    from agent.debate import speak_stream
    from agent.memory import AgentMemory

    # mock LLM: chat_stream yields tokens, chat returns extraction JSON
    mock_llm = AsyncMock()

    async def fake_stream(messages):
        for char in ["国", "电", "南", "瑞", "是"]:
            yield char

    mock_llm.chat_stream = fake_stream
    mock_llm.chat = AsyncMock(return_value=json.dumps({
        "stance": "insist", "confidence": 0.8,
        "challenges": ["质疑1"], "data_requests": [],
        "retail_sentiment_score": None, "speak": True,
    }))

    mock_memory = MagicMock(spec=AgentMemory)
    mock_memory.recall = MagicMock(return_value=[])

    bb = Blackboard(target="600406", debate_id="test", max_rounds=2)
    bb.round = 1

    events = []
    async for event in speak_stream("bull_expert", bb, mock_llm, mock_memory, False):
        events.append(event)

    # 应有 debate_token 事件（5 个字符，一次 flush）+ debate_entry_complete
    token_events = [e for e in events if e["event"] == "debate_token"]
    complete_events = [e for e in events if e["event"] == "debate_entry_complete"]

    assert len(token_events) >= 1
    assert len(complete_events) == 1

    # 完整 argument 应包含所有 token
    assert complete_events[0]["data"]["argument"] == "国电南瑞是"
    assert complete_events[0]["data"]["stance"] == "insist"

    # blackboard 应已更新
    assert len(bb.transcript) == 1


@pytest.mark.asyncio
async def test_speak_stream_handles_llm_interruption():
    """chat_stream 中途异常时，保留部分 argument 并标记中断"""
    from agent.debate import speak_stream
    from agent.memory import AgentMemory

    mock_llm = AsyncMock()

    async def failing_stream(messages):
        yield "部分"
        yield "内容"
        raise ConnectionError("stream broken")

    mock_llm.chat_stream = failing_stream
    mock_llm.chat = AsyncMock(return_value='{"stance":"insist","confidence":0.5,"challenges":[],"data_requests":[],"speak":true}')

    mock_memory = MagicMock(spec=AgentMemory)
    mock_memory.recall = MagicMock(return_value=[])

    bb = Blackboard(target="600406", debate_id="test", max_rounds=2)
    bb.round = 1

    events = []
    async for event in speak_stream("bull_expert", bb, mock_llm, mock_memory, False):
        events.append(event)

    complete = [e for e in events if e["event"] == "debate_entry_complete"][0]
    assert "(发言中断)" in complete["data"]["argument"]
    assert "部分内容" in complete["data"]["argument"]


@pytest.mark.asyncio
async def test_speak_stream_token_batching():
    """token 按 5 个一批或遇标点 flush"""
    from agent.debate import speak_stream
    from agent.memory import AgentMemory

    mock_llm = AsyncMock()

    async def stream_with_punctuation(messages):
        # 12 个 token: 3 + 句号 + 5 + 3
        for t in ["一", "二", "三", "。", "四", "五", "六", "七", "八", "九", "十", "末"]:
            yield t

    mock_llm.chat_stream = stream_with_punctuation
    mock_llm.chat = AsyncMock(return_value='{"stance":"insist","confidence":0.5,"challenges":[],"data_requests":[],"speak":true}')

    mock_memory = MagicMock(spec=AgentMemory)
    mock_memory.recall = MagicMock(return_value=[])

    bb = Blackboard(target="600406", debate_id="test", max_rounds=2)
    bb.round = 1

    events = []
    async for event in speak_stream("bull_expert", bb, mock_llm, mock_memory, False):
        events.append(event)

    token_events = [e for e in events if e["event"] == "debate_token"]
    # 批次: ["一二三。"] (遇句号flush) + ["四五六七八"] (满5) + ["九十末"] (剩余flush)
    assert len(token_events) == 3
    assert token_events[0]["data"]["tokens"] == "一二三。"
    assert token_events[1]["data"]["tokens"] == "四五六七八"
    assert token_events[2]["data"]["tokens"] == "九十末"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd engine && python -m pytest tests/agent/test_debate_stream.py::test_speak_stream_yields_tokens_then_complete -v
```
预期: FAIL (ImportError: cannot import name 'speak_stream')

- [ ] **Step 3: 实现 speak_stream()**

在 `engine/agent/debate.py` 中，`extract_structure()` 之后添加:

```python
async def speak_stream(
    role: str,
    blackboard: Blackboard,
    llm: BaseLLMProvider,
    memory: AgentMemory,
    is_final_round: bool,
) -> AsyncGenerator[dict, None]:
    """流式辩论发言：逐 token 推送 + 结构化后提取"""
    # 构建 messages（与 speak() 一致）
    memory_ctx = memory.recall(role, f"辩论 {blackboard.target}", top_k=3)
    system_prompt = build_debate_system_prompt(role, blackboard.target, is_final_round)
    context = _build_context_for_role(blackboard)
    memory_text = ""
    if memory_ctx:
        memory_text = "\n## 你的历史辩论记忆\n" + "\n".join(
            f"- {m.get('content', '')}" for m in memory_ctx[:3]
        )
    user_content = (
        f"## 当前辩论状态（Round {blackboard.round}）\n\n"
        f"{context}{memory_text}\n\n请发表你的观点。"
    )
    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_content),
    ]

    # Phase 1: 流式输出
    tokens = []
    token_buf = []
    seq = 0

    def _flush_buf():
        nonlocal seq
        if token_buf:
            event = sse("debate_token", {
                "role": role, "round": blackboard.round,
                "tokens": "".join(token_buf), "seq": seq,
            })
            seq += 1
            token_buf.clear()
            return event
        return None

    try:
        async for token in llm.chat_stream(messages):
            tokens.append(token)
            token_buf.append(token)
            if len(token_buf) >= 5 or token in ("。", "\n", ".", "！", "？", "；"):
                ev = _flush_buf()
                if ev:
                    yield ev
        ev = _flush_buf()
        if ev:
            yield ev
    except Exception as e:
        logger.warning(f"流式中断 ({role}): {e}")
        tokens.append("(发言中断)")
        ev = _flush_buf()
        if ev:
            yield ev

    argument = "".join(tokens)

    # Phase 2: 提取结构化字段
    structure = await extract_structure(argument, role, blackboard, llm)

    entry = DebateEntry(
        role=role, round=blackboard.round,
        argument=argument, **structure,
    )

    # Phase 3: blackboard 更新
    if not is_final_round:
        validated = validate_data_requests(role, entry.data_requests)
        blackboard.data_requests.extend(validated)
    blackboard.transcript.append(entry)

    yield sse("debate_entry_complete", entry.model_dump(mode="json"))
```

- [ ] **Step 4: 运行全部流式测试**

```bash
cd engine && python -m pytest tests/agent/test_debate_stream.py -v
```
预期: 6 PASSED (3 extract + 3 speak_stream)

- [ ] **Step 5: 运行全量测试确认无回归**

```bash
cd engine && python -m pytest tests/ -x -q
```
预期: 全部通过

- [ ] **Step 6: 提交**

```bash
git add engine/agent/debate.py engine/tests/agent/test_debate_stream.py
git commit -m "feat: 实现 speak_stream() 逐 token 流式辩论发言"
```

---
### Task 5: run_debate() 适配流式 + 数据请求事件化

**Files:**
- Modify: `engine/agent/debate.py:330-423` (run_debate 重构)
- Modify: `engine/tests/agent/test_debate_e2e.py` (适配新事件)

- [ ] **Step 1: 重构 run_debate() 使用 speak_stream()**

`engine/agent/debate.py` 中 `run_debate()` 函数改动要点:

1. 删除内部 `sse()` 局部函数（已提升到模块级）
2. 多头/空头发言改为 `speak_stream()`:
```python
# 替换原来的 speak() 调用（约第 361-372 行）
# 多头
last_bull = None
async for event in speak_stream("bull_expert", blackboard, llm, memory, is_final):
    yield event
    if event["event"] == "debate_entry_complete":
        last_bull = event["data"]

# 空头
last_bear = None
async for event in speak_stream("bear_expert", blackboard, llm, memory, is_final):
    yield event
    if event["event"] == "debate_entry_complete":
        last_bear = event["data"]
```

3. 观察员发言用缓冲模式处理 `speak=false`:
```python
# 替换原来的观察员循环（约第 375-379 行）
for observer in OBSERVERS:
    buf = []
    async for event in speak_stream(observer, blackboard, llm, memory, is_final):
        buf.append(event)
        if event["event"] == "debate_entry_complete":
            if event["data"].get("speak", True):
                for e in buf:
                    yield e
            buf = []
```

4. concede 检查改为从 event data 读取:
```python
# 替换原来的 concede 检查（约第 397-408 行）
if last_bull and last_bull.get("stance") == "concede":
    blackboard.bull_conceded = True
if last_bear and last_bear.get("stance") == "concede":
    blackboard.bear_conceded = True
```

5. 数据请求处理改为逐个事件化（替换约第 382-394 行）:
```python
# 数据请求逐个事件化
if not is_final and blackboard.data_requests:
    pending = [r for r in blackboard.data_requests if r.status == "pending"]
    import time

    async def _process_one(req):
        t0 = time.monotonic()
        req_id = f"{req.requested_by}_{req.action}_{req.round}"
        yield sse("data_request_start", {
            "requested_by": req.requested_by,
            "engine": req.engine,
            "action": req.action,
            "params": req.params,
            "request_id": req_id,
        })
        try:
            result = await data_fetcher.fetch_by_request(req)
            req.result = result
            req.status = "done"
            duration = int((time.monotonic() - t0) * 1000)
            summary = str(result)[:200] if result else ""
            yield sse("data_request_done", {
                "request_id": req_id, "engine": req.engine,
                "action": req.action, "status": "done",
                "result_summary": summary, "duration_ms": duration,
            })
        except Exception as e:
            req.status = "failed"
            duration = int((time.monotonic() - t0) * 1000)
            yield sse("data_request_done", {
                "request_id": req_id, "engine": req.engine,
                "action": req.action, "status": "failed",
                "result_summary": str(e)[:200], "duration_ms": duration,
            })

    success = 0
    failed = 0
    for req in pending:
        async for ev in _process_one(req):
            yield ev
        if req.status == "done":
            success += 1
        else:
            failed += 1

    yield sse("data_batch_complete", {
        "round": blackboard.round,
        "total": len(pending),
        "success": success,
        "failed": failed,
    })
```

- [ ] **Step 2: 适配 test_debate_e2e.py**

`engine/tests/agent/test_debate_e2e.py` 中的 mock 需要更新:

1. mock LLM 增加 `chat_stream` 方法（返回 async generator）
2. 事件断言从 `debate_entry` 改为 `debate_token` + `debate_entry_complete`
3. 数据请求事件从 `data_fetching`/`data_ready` 改为 `data_request_start`/`data_request_done`/`data_batch_complete`

```python
# mock LLM 的 chat_stream
async def mock_chat_stream(messages):
    response = mock_chat_response(messages)  # 复用现有 mock 逻辑
    for char in response:
        yield char

mock_llm.chat_stream = mock_chat_stream
```

- [ ] **Step 3: 运行 E2E 测试**

```bash
cd engine && python -m pytest tests/agent/test_debate_e2e.py -v
```
预期: 3 PASSED

- [ ] **Step 4: 运行全量测试**

```bash
cd engine && python -m pytest tests/ -x -q
```
预期: 全部通过

- [ ] **Step 5: 提交**

```bash
git add engine/agent/debate.py engine/tests/agent/test_debate_e2e.py
git commit -m "feat: run_debate() 适配流式发言 + 数据请求逐个事件化"
```

---

### Task 6: judge_summarize_stream() 流式化

**Files:**
- Modify: `engine/agent/debate.py:216-273` (judge 流式化)
- Modify: `engine/tests/agent/test_debate_stream.py` (新增 judge 测试)

- [ ] **Step 1: 写失败测试**

在 `engine/tests/agent/test_debate_stream.py` 追加:

```python
@pytest.mark.asyncio
async def test_judge_streaming():
    """judge_summarize_stream 先 yield judge_token，最后 yield judge_verdict"""
    from agent.debate import judge_summarize_stream
    from agent.memory import AgentMemory

    mock_llm = AsyncMock()

    async def fake_stream(messages):
        for char in ["综", "合", "来", "看", "。"]:
            yield char

    mock_llm.chat_stream = fake_stream
    # judge 的结构化提取仍用 chat()，返回 JSON
    mock_llm.chat = AsyncMock(return_value=json.dumps({
        "summary": "综合来看。",
        "signal": "bearish", "score": -0.5,
        "key_arguments": ["论据1"],
        "bull_core_thesis": "多头论点",
        "bear_core_thesis": "空头论点",
        "retail_sentiment_note": "散户中性",
        "smart_money_note": "主力谨慎",
        "risk_warnings": ["风险1"],
        "debate_quality": "strong_disagreement",
    }))

    mock_memory = MagicMock(spec=AgentMemory)
    mock_memory.recall = MagicMock(return_value=[])
    mock_memory.store = MagicMock()

    bb = Blackboard(target="600406", debate_id="test_123", max_rounds=2)
    bb.round = 2
    bb.status = "judging"

    events = []
    async for event in judge_summarize_stream(bb, mock_llm, mock_memory):
        events.append(event)

    token_events = [e for e in events if e["event"] == "judge_token"]
    verdict_events = [e for e in events if e["event"] == "judge_verdict"]

    assert len(token_events) >= 1
    assert len(verdict_events) == 1
    assert verdict_events[0]["data"]["signal"] == "bearish"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd engine && python -m pytest tests/agent/test_debate_stream.py::test_judge_streaming -v
```
预期: FAIL (ImportError)

- [ ] **Step 3: 实现 judge_summarize_stream()**

在 `engine/agent/debate.py` 中，现有 `judge_summarize()` 之后添加:

```python
async def judge_summarize_stream(
    blackboard: Blackboard,
    llm: BaseLLMProvider,
    memory: AgentMemory,
) -> AsyncGenerator[dict, None]:
    """流式裁判总结：逐 token 推送 summary，最后提取结构化裁决"""
    memory_ctx = memory.recall("judge", f"辩论 {blackboard.target}", top_k=3)
    context = _build_context_for_role(blackboard)
    memory_text = ""
    if memory_ctx:
        memory_text = "\n## 历史裁决参考\n" + "\n".join(
            f"- {m.get('content', '')}" for m in memory_ctx[:3]
        )

    # judge 的流式 prompt: 先输出自然语言总结
    judge_stream_prompt = (
        f"你是一位专业的股票辩论裁判。请对以下辩论做出总结评价，"
        f"直接用自然语言阐述你的裁决。\n\n{context}{memory_text}"
    )
    messages = [
        ChatMessage(role="system", content=JUDGE_SYSTEM_PROMPT),
        ChatMessage(role="user", content=judge_stream_prompt),
    ]

    # Phase 1: 流式输出 summary
    tokens = []
    token_buf = []
    seq = 0
    try:
        async for token in llm.chat_stream(messages):
            tokens.append(token)
            token_buf.append(token)
            if len(token_buf) >= 5 or token in ("。", "\n", ".", "！", "？", "；"):
                yield sse("judge_token", {
                    "role": "judge", "round": None,
                    "tokens": "".join(token_buf), "seq": seq,
                })
                seq += 1
                token_buf = []
        if token_buf:
            yield sse("judge_token", {
                "role": "judge", "round": None,
                "tokens": "".join(token_buf), "seq": seq,
            })
    except Exception as e:
        logger.warning(f"裁判流式中断: {e}")
        tokens.append("(裁决中断)")

    summary_text = "".join(tokens)

    # Phase 2: 提取结构化裁决（用现有 judge prompt 格式）
    try:
        verdict = await asyncio.wait_for(
            _extract_judge_verdict(summary_text, blackboard, llm),
            timeout=30.0,
        )
    except Exception:
        verdict = _fallback_verdict(blackboard, summary_text)

    # 存储记忆
    memory.store("judge", f"裁决 {blackboard.target}: {verdict.signal} ({verdict.score})",
                 {"debate_id": blackboard.debate_id})

    yield sse("judge_verdict", verdict.model_dump(mode="json"))
```

同时添加辅助函数 `_extract_judge_verdict()`:
```python
async def _extract_judge_verdict(
    summary: str, blackboard: Blackboard, llm: BaseLLMProvider
) -> JudgeVerdict:
    """从 summary 文本提取结构化 JudgeVerdict"""
    extract_prompt = f"""请从以下裁判总结中提取结构化裁决，只返回 JSON:

{summary}

返回格式: {JUDGE_JSON_SCHEMA}"""

    raw = await llm.chat([ChatMessage(role="user", content=extract_prompt)])
    json_str = _extract_json(raw)
    data = json.loads(json_str)
    return _parse_judge_output_from_dict(data, blackboard)
```

- [ ] **Step 4: 更新 run_debate() 使用 judge_summarize_stream()**

`run_debate()` 中约第 417-419 行:
```python
# 替换
# verdict = await judge_summarize(blackboard, llm, memory)
# yield sse("judge_verdict", verdict.model_dump(mode="json"))
# 改为
async for event in judge_summarize_stream(blackboard, llm, memory):
    yield event
```

- [ ] **Step 5: 运行测试**

```bash
cd engine && python -m pytest tests/agent/test_debate_stream.py -v
cd engine && python -m pytest tests/ -x -q
```
预期: 全部通过

- [ ] **Step 6: 提交**

```bash
git add engine/agent/debate.py engine/tests/agent/test_debate_stream.py
git commit -m "feat: judge_summarize_stream() 裁判流式输出"
```

---

### Task 7: SSE 端点适配

**Files:**
- Modify: `engine/api/routes/debate.py`

- [ ] **Step 1: 确认无需改动**

`debate.py` 路由已经是通用的 SSE 转发:
```python
async for event in run_debate(...):
    yield f"event: {event['event']}\ndata: {json.dumps(event['data'], ...)}\n\n"
```

新事件类型（`debate_token`、`debate_entry_complete`、`judge_token`、`data_request_start` 等）会自动通过，无需修改路由代码。

- [ ] **Step 2: 验证**

```bash
cd engine && python -m pytest tests/ -x -q
```

- [ ] **Step 3: 提交（如有改动）**

如果无改动则跳过此步。

---

## Chunk 2: MCP Streamable HTTP Transport 迁移

### Task 8: pyproject.toml 版本约束 + __main__.py 迁移

**Files:**
- Modify: `engine/pyproject.toml`
- Modify: `engine/mcpserver/__main__.py`
- Modify: `engine/mcpserver/server.py` (main 函数)

- [ ] **Step 1: 更新 pyproject.toml**

将 `mcp>=1.0.0` 改为 `mcp>=1.26.0`。

- [ ] **Step 2: 修改 server.py 的 main() 函数**

找到 `server.py` 底部的 `main()` 函数，修改 transport:

```python
def main():
    import os
    server.settings.host = os.getenv("MCP_HOST", "0.0.0.0")
    server.settings.port = int(os.getenv("MCP_PORT", "8001"))
    server.run(transport="streamable-http")
```

- [ ] **Step 3: 更新 .mcp.json**

```json
{
  "mcpServers": {
    "stockterrain": {
      "url": "http://localhost:8001/mcp"
    },
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"]
    }
  }
}
```

- [ ] **Step 4: 验证 MCP server 能启动**

```bash
cd engine && timeout 5 .venv/bin/python -m mcpserver || true
```
预期: 看到 uvicorn 启动日志，监听 8001 端口

- [ ] **Step 5: 提交**

```bash
git add engine/pyproject.toml engine/mcpserver/server.py .mcp.json
git commit -m "feat: MCP server 迁移到 Streamable HTTP transport (端口 8001)"
```

---

### Task 9: start_debate 异步化 + notification 推送

**Files:**
- Modify: `engine/mcpserver/server.py:174-177` (async + ctx)
- Modify: `engine/mcpserver/tools.py` (新增 start_debate_async, 删除旧 start_debate)

- [ ] **Step 1: 修改 server.py 的 start_debate 注册**

```python
from mcp.server.fastmcp import Context

@server.tool()
async def start_debate(code: str | int, max_rounds: int = 3, ctx: Context = None) -> str:
    """发起专家辩论（多头 vs 空头 + 散户/主力观察员 + 裁判）。需要后端在线且配置 LLM API Key。code 示例: '600519'"""
    return await tools.start_debate_async(_da, str(code), max_rounds, ctx)
```

- [ ] **Step 2: 在 tools.py 中实现 start_debate_async()**

在 `engine/mcpserver/tools.py` 中，删除现有的同步 `start_debate()` 函数（第 1161-1306 行），替换为:

```python
async def start_debate_async(da: "DataAccess", code: str, max_rounds: int, ctx=None) -> str:
    """发起专家辩论 — 异步消费 SSE 流，通过 MCP notification 实时推送"""
    import httpx

    if not da.is_online():
        return json.dumps({
            "error": "后端未运行，无法发起辩论",
            "hint": "请先启动 engine: `cd engine && python main.py`",
        }, ensure_ascii=False, indent=2)

    ROLE_NAMES = {
        "bull_expert": "多头专家", "bear_expert": "空头专家",
        "retail_investor": "散户代表", "smart_money": "主力代表",
    }

    try:
        lines = []
        debate_id = None

        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as client:
            async with client.stream(
                "POST", f"{da._api_base}/api/v1/debate",
                json={"code": code, "max_rounds": max_rounds},
            ) as resp:
                resp.raise_for_status()
                event_type = None
                data_buf = ""

                async for line in resp.aiter_lines():
                    if line.startswith("event: "):
                        event_type = line[7:].strip()
                    elif line.startswith("data: "):
                        data_buf = line[6:]
                    elif line == "" and event_type and data_buf:
                        try:
                            data = json.loads(data_buf)
                        except json.JSONDecodeError:
                            event_type = None
                            data_buf = ""
                            continue

                        if event_type == "debate_start":
                            debate_id = data.get("debate_id")
                            lines.append(f"# 专家辩论: {code}")
                            lines.append(f"debate_id: `{debate_id}` | max_rounds: {data.get('max_rounds')}")
                            lines.append("")

                        elif event_type == "debate_round_start":
                            rd = data.get("round", 0)
                            is_final = data.get("is_final", False)
                            lines.append("---")
                            lines.append(f"## Round {rd}" + (" (最终轮)" if is_final else ""))
                            lines.append("")

                        elif event_type == "debate_token":
                            role = data.get("role", "")
                            role_cn = ROLE_NAMES.get(role, role)
                            tokens_text = data.get("tokens", "")
                            if ctx:
                                await ctx.log("info", f"[{role_cn}] {tokens_text}")

                        elif event_type == "debate_entry_complete":
                            role = data.get("role", "")
                            role_cn = ROLE_NAMES.get(role, role)
                            stance = data.get("stance")
                            conf = data.get("confidence", 0)
                            arg = data.get("argument", "")
                            challenges = data.get("challenges", [])
                            sentiment = data.get("retail_sentiment_score")

                            header = f"### {role_cn}"
                            if stance:
                                header += f" [{stance}]"
                            header += f" (confidence={conf:.2f})"
                            if sentiment is not None:
                                header += f" | 情绪={sentiment:+.2f}"
                            lines.append(header)
                            lines.append("")
                            if arg:
                                lines.append(arg)
                                lines.append("")
                            if challenges:
                                lines.append("**质疑:**")
                                for i, c in enumerate(challenges, 1):
                                    lines.append(f"{i}. {c}")
                                lines.append("")
                            if ctx:
                                await ctx.log("info", f"✅ {role_cn} 发言完毕 (confidence={conf:.2f})")

                        elif event_type == "data_request_start":
                            if ctx:
                                await ctx.log("info",
                                    f"📊 [{ROLE_NAMES.get(data.get('requested_by',''), data.get('requested_by',''))}] "
                                    f"→ {data.get('engine')}.{data.get('action')}()")
                            lines.append(f"> 📊 数据请求: {data.get('engine')}.{data.get('action')} "
                                        f"(by {ROLE_NAMES.get(data.get('requested_by',''), data.get('requested_by',''))})")

                        elif event_type == "data_request_done":
                            status_icon = "✅" if data.get("status") == "done" else "❌"
                            if ctx:
                                await ctx.log("info",
                                    f"{status_icon} {data.get('action')} ({data.get('duration_ms', 0)}ms)")
                            lines.append(f"> {status_icon} {data.get('action')} "
                                        f"({data.get('duration_ms', 0)}ms): {data.get('result_summary', '')}")

                        elif event_type == "data_batch_complete":
                            if ctx:
                                await ctx.log("info",
                                    f"📋 数据请求完毕: {data.get('success')}/{data.get('total')} 成功")
                            lines.append("")

                        elif event_type == "judge_token":
                            tokens_text = data.get("tokens", "")
                            if ctx:
                                await ctx.log("info", f"[裁判] {tokens_text}")

                        elif event_type == "debate_end":
                            reason = data.get("reason", "")
                            rounds = data.get("rounds_completed", 0)
                            lines.append("---")
                            lines.append(f"辩论结束 | 完成 {rounds} 轮 | 终止原因: {reason}")
                            lines.append("")

                        elif event_type == "judge_verdict":
                            lines.append("---")
                            lines.append("# 裁判裁决")
                            lines.append("")
                            lines.append(data.get("summary", ""))
                            lines.append("")
                            signal = data.get("signal")
                            score = data.get("score")
                            if signal:
                                score_str = f" (score={score:.2f})" if score is not None else ""
                                lines.append(f"**信号: {signal}{score_str}**")
                                lines.append("")
                            lines.append(f"**多头核心论点:** {data.get('bull_core_thesis', '')}")
                            lines.append("")
                            lines.append(f"**空头核心论点:** {data.get('bear_core_thesis', '')}")
                            lines.append("")
                            lines.append(f"**散户情绪参考:** {data.get('retail_sentiment_note', '')}")
                            lines.append("")
                            lines.append(f"**主力资金动向:** {data.get('smart_money_note', '')}")
                            lines.append("")
                            lines.append(f"**辩论质量:** {data.get('debate_quality', '')}")
                            lines.append("")
                            warnings = data.get("risk_warnings", [])
                            if warnings:
                                lines.append("**风险提示:**")
                                for i, w in enumerate(warnings, 1):
                                    lines.append(f"{i}. {w}")
                                lines.append("")
                            key_args = data.get("key_arguments", [])
                            if key_args:
                                lines.append("**关键论据:**")
                                for i, a in enumerate(key_args, 1):
                                    lines.append(f"{i}. {a}")

                        elif event_type == "error":
                            return json.dumps({"error": data.get("message", "辩论失败")}, ensure_ascii=False)

                        event_type = None
                        data_buf = ""

        return "\n".join(lines)

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 503:
            return json.dumps({"error": "LLM 未配置，请先在 .env 中设置 API Key"}, ensure_ascii=False)
        return json.dumps({"error": f"辩论请求失败: {e}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"辩论失败: {e}"}, ensure_ascii=False)
```

- [ ] **Step 3: 语法检查**

```bash
python3 -c "import py_compile; py_compile.compile('engine/mcpserver/tools.py', doraise=True); print('OK')"
python3 -c "import py_compile; py_compile.compile('engine/mcpserver/server.py', doraise=True); print('OK')"
```

- [ ] **Step 4: 运行全量测试**

```bash
cd engine && python -m pytest tests/ -x -q
```

- [ ] **Step 5: 提交**

```bash
git add engine/mcpserver/server.py engine/mcpserver/tools.py
git commit -m "feat: start_debate 异步化 + MCP notification 实时推送辩论过程"
```

---

### Task 10: MCP HTTP Transport 集成测试

**Files:**
- Create: `engine/tests/mcpserver/test_http_transport.py`

- [ ] **Step 1: 写集成测试**

```python
# engine/tests/mcpserver/test_http_transport.py
"""MCP Streamable HTTP transport 基础验证"""
import pytest


def test_mcp_server_imports():
    """验证 MCP server 模块可正常导入"""
    from mcpserver.server import server
    assert server is not None


def test_mcp_streamable_http_app():
    """验证 FastMCP 能生成 streamable-http ASGI app"""
    from mcpserver.server import server
    app = server.streamable_http_app()
    assert app is not None


def test_mcp_tools_registered():
    """验证 22 个 tool 已注册"""
    from mcpserver.server import server
    # FastMCP 的 tool 列表
    tools = server._tool_manager._tools
    assert len(tools) >= 22
```

- [ ] **Step 2: 运行测试**

```bash
cd engine && python -m pytest tests/mcpserver/test_http_transport.py -v
```

- [ ] **Step 3: 提交**

```bash
git add engine/tests/mcpserver/test_http_transport.py
git commit -m "test: MCP HTTP transport 基础集成测试"
```

---

### Task 11: 端到端验证

- [ ] **Step 1: 启动后端**

```bash
cd engine && python main.py &
```

- [ ] **Step 2: 启动 MCP HTTP server**

```bash
cd engine && python -m mcpserver &
```
验证: 看到 uvicorn 监听 8001

- [ ] **Step 3: curl 测试辩论 SSE 流**

```bash
curl -s -N -X POST http://localhost:8000/api/v1/debate \
  -H "Content-Type: application/json" \
  -d '{"code": "600406", "max_rounds": 1}' | head -50
```
验证: 看到 `debate_token` 事件逐批推送

- [ ] **Step 4: 运行全量测试**

```bash
cd engine && python -m pytest tests/ -x -q
```
预期: 全部通过

- [ ] **Step 5: 最终提交**

```bash
git add -A
git commit -m "feat: 流式辩论 + MCP Streamable HTTP transport 完成"
```
