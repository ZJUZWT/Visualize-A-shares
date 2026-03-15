# 流式辩论 + MCP Streamable HTTP Transport 设计

日期: 2026-03-15
状态: Draft

## 背景

当前辩论系统存在两个问题：
1. LLM 调用使用非流式 `chat()`，45 秒超时导致长论点被截断（多头 timeout）
2. MCP 工具使用 stdio transport，tool 调用只能等全部结束才返回结果，用户体验差

目标：辩论过程逐 token 实时输出，MCP 迁移到 Streamable HTTP transport 支持中间结果推送。

## 前置修复

以下 bug 必须在流式改造之前修复，否则 `chat_stream()` 无法正常工作：

`engine/llm/providers.py` AnthropicProvider.chat_stream() 第 186 行调用了不存在的方法：
```python
# 现在（bug）
url = f"{self._get_base_url()}/v1/messages"

# 修复
url = f"{self.config.base_url.rstrip('/')}/v1/messages"
```

## 决策记录

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 流式粒度 | 逐 token（逐字） | 体验最好，像 ChatGPT 一样逐字蹦出 |
| JSON 解析策略 | 正文流式 + 结构后提取 | LLM 输出改为纯自然语言，结构化字段完成后单独提取 |
| MCP transport | 完全迁移到 Streamable HTTP | 长期方向，支持 notification 推送中间结果 |
| 架构模式 | MCP HTTP 独立进程（方案 A） | MCP 和后端解耦，符合现有架构 |
| Token 推送策略 | 批量推送（每 5 token 或 50ms） | 减少 SSE/notification 开销，避免背压问题 |

## 第一部分：辩论流式改造

### 1.1 speak() 函数重构

`engine/agent/debate.py` 中的 `speak()` 从同步返回改为 async generator `speak_stream()`。

函数签名与现有 `speak()` 一致，增加 async generator 返回：

```python
async def speak_stream(
    role: str,
    blackboard: Blackboard,
    llm: BaseLLMProvider,
    memory: AgentMemory,
    is_final_round: bool,
) -> AsyncGenerator[dict, None]:
    # 构建 messages（与现有 speak() 一致，使用相同的 helper 函数）
    mem_context = memory.recall(role, f"辩论 {blackboard.target}", top_k=3)
    system_prompt = build_debate_system_prompt(role, blackboard.target, is_final_round)
    context = _build_context_for_role(blackboard)
    # 内联格式化记忆（与现有 speak() 一致，不引入新 helper）
    memory_text = ""
    if mem_context:
        memory_text = "\n## 你的历史辩论记忆\n" + "\n".join(
            f"- {m.get('content', '')}" for m in mem_context[:3]
        )
    user_content = f"## 当前辩论状态（Round {blackboard.round}）\n\n{context}{memory_text}\n\n请发表你的观点。"
    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_content),
    ]

    # Phase 1: 流式输出 argument 正文
    # 注意：sse() 需提升为模块级函数（现在是 run_debate() 内的局部函数）
    tokens = []
    token_buf = []
    seq = 0
    try:
        async for token in llm.chat_stream(messages):
            tokens.append(token)
            token_buf.append(token)
            # 批量推送：每 5 个 token 或遇到句号/换行时 flush
            if len(token_buf) >= 5 or token in ("。", "\n", ".", "！", "？"):
                yield sse("debate_token", {
                    "role": role, "round": blackboard.round,
                    "tokens": "".join(token_buf), "seq": seq,
                })
                seq += 1
                token_buf = []
        # flush 剩余 token
        if token_buf:
            yield sse("debate_token", {
                "role": role, "round": blackboard.round,
                "tokens": "".join(token_buf), "seq": seq,
            })
    except Exception as e:
        logger.warning(f"流式中断 ({role}): {e}")
        tokens.append("(发言中断)")

    argument = "".join(tokens)

    # Phase 2: 轻量 LLM 调用提取结构化字段
    structure = await extract_structure(argument, role, blackboard, llm)

    entry = DebateEntry(role=role, round=blackboard.round, argument=argument, **structure)

    # Phase 3: data_requests 验证 + blackboard 更新
    # 注意：speak_stream() 内部负责 blackboard 更新，run_debate() 不再重复 append
    if not is_final_round:
        validated = validate_data_requests(role, entry.data_requests)
        blackboard.data_requests.extend(validated)
    blackboard.transcript.append(entry)

    yield sse("debate_entry_complete", entry.model_dump())
    # run_debate() 通过检查最后一个 debate_entry_complete 事件的 stance 字段判断 concede
```

**重要变更：`run_debate()` 中的 blackboard 操作迁移**

现有 `run_debate()` 在调用 `speak()` 后自行执行 `blackboard.transcript.append(entry)` 和 concede 检查。改造后这些逻辑移入 `speak_stream()` 内部。`run_debate()` 的适配：

```python
# 改后的 run_debate() 循环
last_entry = None
async for event in speak_stream(role, blackboard, llm, memory, is_final):
    yield event
    if event["event"] == "debate_entry_complete":
        last_entry = event["data"]

# concede 检查（从 event data 中读取 stance，不再从 DebateEntry 对象读取）
if last_entry and last_entry.get("stance") == "concede":
    if role == "bull_expert":
        blackboard.bull_conceded = True
    elif role == "bear_expert":
        blackboard.bear_conceded = True
```

### 1.2 extract_structure() 定义

新增函数，负责从完整 argument 文本中提取结构化字段：

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
  "speak": true 或 false（observer 角色可选择沉默，debater 角色始终为 true）
}}"""

    try:
        raw = await asyncio.wait_for(
            llm.chat([ChatMessage(role="user", content=extract_prompt)]),
            timeout=10.0,
        )
        parsed = json.loads(raw)
        return {
            "stance": parsed.get("stance", "insist"),
            "confidence": float(parsed.get("confidence", 0.5)),
            "challenges": parsed.get("challenges", []),
            "data_requests": [
                DataRequest(requested_by=role, round=blackboard.round,
                            status="pending", **dr)
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

提取调用使用 `chat()`（非流式），返回内容短（几百 token），1-3 秒完成。默认使用主模型，可通过 `LLM_EXTRACT_MODEL` 环境变量切换为更快/更便宜的模型。

### 1.3 LLM Prompt 改造

`engine/agent/personas.py` 中的辩论 prompt 改为两阶段：

**阶段 1（流式，主 prompt）：** 要求 LLM 直接输出自然语言论点，不包裹 JSON。移除现有 prompt 中的 JSON 格式要求，改为"请直接阐述你的观点和论据"。

**阶段 2（非流式，提取 prompt）：** 见上方 `extract_structure()` 中的 `extract_prompt`。

### 1.4 SSE 事件流变化

```
现在：debate_round_start → [等45秒] → debate_entry → [等45秒] → debate_entry → ...
改后：debate_round_start → debate_token* → debate_entry_complete → debate_token* → ...
```

新增事件类型：

| 事件 | 数据格式 | 说明 |
|------|----------|------|
| `debate_token` | `{"role": str, "round": int, "tokens": str, "seq": int}` | 批量 token（每 5 个或遇标点 flush） |
| `debate_entry_complete` | 同现有 `debate_entry` | 含完整结构化数据 |
| `judge_token` | `{"role": "judge", "round": null, "tokens": str, "seq": int}` | 裁判发言的批量 token |

保留事件：`debate_start`、`debate_round_start`、`debate_end`、`judge_verdict`、`error`。

移除事件：`debate_entry`（被 `debate_token` + `debate_entry_complete` 替代）。`data_fetching` 和 `data_ready` 拆分为更细粒度的事件（见下方 1.7）。

`debate_token` 和 `judge_token` 格式一致，区别仅在 `role` 字段。前端可统一处理。

### 1.7 数据请求详细事件

现有 `data_fetching` 和 `data_ready` 只给出粗粒度信息（"正在请求"/"已完成 N 条"），无法监控每个引擎专家的具体行为。拆分为以下事件：

| 事件 | 数据格式 | 说明 |
|------|----------|------|
| `data_request_start` | `{"requested_by": str, "engine": str, "action": str, "params": dict, "request_id": str}` | 单个数据请求开始，路由到具体引擎 |
| `data_request_done` | `{"request_id": str, "engine": str, "action": str, "status": "done"\|"failed", "result_summary": str, "duration_ms": int}` | 单个数据请求完成，含结果摘要和耗时 |
| `data_batch_complete` | `{"round": int, "total": int, "success": int, "failed": int}` | 本轮所有数据请求处理完毕的汇总 |

事件序列示例：
```
debate_entry_complete (多头，含 3 个 data_requests)
debate_entry_complete (空头，含 2 个 data_requests)
debate_entry_complete (主力代表，含 1 个 data_request)
→ data_request_start (多头请求 get_factor_scores → quant 引擎)
→ data_request_start (空头请求 get_valuation_history → quant 引擎)
→ data_request_start (主力请求 get_technical_indicators → quant 引擎)
→ data_request_done (get_factor_scores, done, 1.2s)
→ data_request_start (多头请求 get_financial_summary → data 引擎)
→ data_request_done (get_valuation_history, done, 0.8s)
→ data_request_done (get_technical_indicators, done, 0.9s)
→ data_request_start (空头请求 get_financial_trend → data 引擎)
→ data_request_done (get_financial_summary, done, 1.1s)
→ data_request_done (get_financial_trend, failed, 2.0s)
→ data_batch_complete (round=1, total=6, success=5, failed=1)
```

实现位置：`run_debate()` 中现有的 `_process_data_requests()` 调用改为逐个请求 yield 事件。每个请求并发执行（`asyncio.gather`），完成时立即 yield `data_request_done`。

MCP notification 推送：`start_debate_async()` 中对这些事件同样通过 `ctx.log()` 推送：
```python
elif event_type == "data_request_start":
    if ctx:
        await ctx.log("info",
            f"📊 [{data['requested_by']}] → {data['engine']}.{data['action']}({data.get('params', {})})")
elif event_type == "data_request_done":
    status_icon = "✅" if data["status"] == "done" else "❌"
    if ctx:
        await ctx.log("info",
            f"{status_icon} {data['action']} ({data['duration_ms']}ms): {data.get('result_summary', '')}")
elif event_type == "data_batch_complete":
    if ctx:
        await ctx.log("info",
            f"📋 数据请求完毕: {data['success']}/{data['total']} 成功, {data['failed']} 失败")
```

### 1.5 run_debate() 适配

```python
# 现在
entry = await speak(role, blackboard, llm, memory, is_final)
yield sse("debate_entry", entry.model_dump())

# 改后（注意：不再在 run_debate() 中 append transcript，speak_stream() 内部已处理）
last_entry = None
async for event in speak_stream(role, blackboard, llm, memory, is_final):
    yield event
    if event["event"] == "debate_entry_complete":
        last_entry = event["data"]
# concede 检查从 last_entry["stance"] 读取
```

**前置重构：`sse()` 提升为模块级函数。** 现有 `sse()` 是 `run_debate()` 内的局部函数，`speak_stream()` 作为独立函数无法访问。将其提升到 `debate.py` 模块顶层：

```python
# debate.py 模块级
def sse(event: str, data: dict) -> dict:
    return {"event": event, "data": data}
```

judge 的 `judge_summarize()` 同样改为流式 `judge_summarize_stream()`，yield `judge_token` 事件，最后 yield `judge_verdict`。结构与 `speak_stream()` 类似：先流式输出 summary 正文，再提取结构化裁决字段。

**Observer silence 处理：** 现有逻辑中 observer（retail_investor、smart_money）可能返回 `speak: false` 表示本轮沉默。流式改造后，`extract_structure()` 的返回 schema 增加 `speak` 字段。`run_debate()` 在收到 `debate_entry_complete` 后检查 `speak` 字段：如果为 `false`，不向外层 yield 该角色的 `debate_token` 和 `debate_entry_complete` 事件。实现方式：`run_debate()` 对 observer 角色先缓冲 `speak_stream()` 的事件，提取完成后根据 `speak` 字段决定是否 flush 缓冲区：

```python
# observer 角色的特殊处理
buf = []
async for event in speak_stream(observer, blackboard, llm, memory, is_final):
    buf.append(event)
    if event["event"] == "debate_entry_complete":
        if event["data"].get("speak", True):
            for e in buf:
                yield e  # flush 全部事件
        # speak=false 时不 yield，但 blackboard 已在 speak_stream() 内更新
```

### 1.6 Token 批量推送策略

单个 token 逐一推送会产生大量 SSE 事件（4 角色 × ~1000 token × 2 轮 ≈ 8000 事件）。

策略：缓冲 token，满足以下任一条件时 flush：
- 缓冲区达到 5 个 token
- 遇到句号、换行、问号、感叹号等标点

事件数量降低约 5 倍（~1600 事件），保持逐句级别的实时感。`debate_token` 事件的 `tokens` 字段为批量拼接的字符串。

## 第二部分：MCP Streamable HTTP Transport 迁移

### 2.1 MCP Server HTTP 化

`engine/mcpserver/__main__.py` 启动方式变更：

```python
# 现在
server.run(transport="stdio")

# 改后
import os
server.settings.host = os.getenv("MCP_HOST", "0.0.0.0")
server.settings.port = int(os.getenv("MCP_PORT", "8001"))
server.run(transport="streamable-http")
```

使用 FastMCP 内置的 `run(transport="streamable-http")`，自动创建 `StreamableHTTPSessionManager`、配置路由和 lifespan、启动 uvicorn。无需手动构建 ASGI app。

### 2.2 .mcp.json 配置变更

仅修改 `stockterrain` 条目，保留其他 MCP server（如 `memory`）：

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

### 2.3 MCP Tool 同步→异步迁移

当前 `engine/mcpserver/server.py` 中所有 tool 都是同步函数。为了在 `start_debate` 中使用 `await ctx.log()`，需要将其改为 `async def` 并接收 `Context` 参数：

```python
from mcp.server.fastmcp import Context

# 现在
@server.tool()
def start_debate(code: str | int, max_rounds: int = 3) -> str:
    return tools.start_debate(_da, str(code), max_rounds)

# 改后
@server.tool()
async def start_debate(code: str | int, max_rounds: int = 3, ctx: Context = None) -> str:
    return await tools.start_debate_async(_da, str(code), max_rounds, ctx)
```

其他不需要 notification 的 tool 保持同步不变。仅 `start_debate` 需要异步化。

### 2.4 辩论 tool 的 notification 推送

notification 推送逻辑在 `engine/mcpserver/tools.py` 的新函数 `start_debate_async()` 中（需要 `ctx` 参数）。`server.py` 传递 `ctx`，`tools.py` 实现：

```python
# engine/mcpserver/tools.py
async def start_debate_async(da: "DataAccess", code: str, max_rounds: int, ctx) -> str:
    import httpx
    lines = []
    async with httpx.AsyncClient(timeout=600.0) as client:
        async with client.stream(
            "POST", f"{da._api_base}/api/v1/debate",
            json={"code": code, "max_rounds": max_rounds},
        ) as resp:
            resp.raise_for_status()
            async for event_type, data in _parse_sse_async(resp):
                if event_type == "debate_token":
                    if ctx:
                        await ctx.log("info", f"[{data.get('role')}] {data.get('tokens', '')}")
                elif event_type == "debate_entry_complete":
                    lines.append(_format_entry(data))
                    if ctx:
                        await ctx.log("info", f"✅ {data.get('role')} 发言完毕")
                elif event_type == "judge_token":
                    if ctx:
                        await ctx.log("info", f"[裁判] {data.get('tokens', '')}")
                elif event_type == "judge_verdict":
                    lines.append(_format_verdict(data))
                # ... 其他事件同现有逻辑
    return "\n".join(lines)
```

`ctx.log("info", message)` 调用 MCP 协议的 `notifications/message`，Claude Code 实时显示。tool 最终返回值仍然是完整 Markdown 辩论记录（向后兼容）。

**旧函数处理：** `tools.py` 中现有的同步 `start_debate()` 函数删除，由 `start_debate_async()` 完全替代。其他 debate 相关 tool（`get_debate_status`、`get_debate_transcript`、`get_judge_verdict`）保持同步不变——它们只做简单的 HTTP GET 请求，不需要 notification 推送。

### 2.5 端口与启动

| 服务 | 端口 | 启动命令 |
|------|------|----------|
| FastAPI 后端 | 8000 | `cd engine && python main.py` |
| MCP HTTP server | 8001 | `cd engine && python -m mcpserver` |
| Next.js 前端 | 3000 | `cd web && npm run dev` |

### 2.6 依赖版本约束

`engine/pyproject.toml` 中 `mcp>=1.0.0` 提升为 `mcp>=1.26.0`，因为 Streamable HTTP transport 和 `Context.log()` 是 1.26.0 的功能。

## 第三部分：错误处理与降级

### 3.1 LLM 流式中断

- 已收到的 token 拼成部分 argument，追加 `(发言中断)` 标记
- 跳过结构化提取，使用 fallback 默认值
- yield `debate_entry_complete` 带部分内容，辩论继续下一个角色

### 3.2 结构化提取失败

- 提取 LLM 调用超时（10 秒）或返回无效 JSON（包括 parse error）
- fallback：`stance="insist"`、`confidence=0.5`、其余为空
- argument 正文不受影响（已流式输出完毕）

### 3.3 MCP HTTP 连接断开

- 辩论在后端继续执行完毕，结果持久化到 DuckDB
- 客户端重连后通过 `get_debate_transcript` 拉取完整记录

### 3.4 后端 SSE 断开

- MCP tool 返回已收到的部分内容 + 错误提示
- 用户可通过 `get_debate_transcript` 补拉

## 第四部分：测试策略

### 4.1 单元测试

| 测试 | 验证点 |
|------|--------|
| `test_speak_streaming` | mock `chat_stream()` yield token，验证 `debate_token` 批量产出，`debate_entry_complete` 包含完整 argument |
| `test_structure_extraction` | mock 提取 LLM 调用，验证 stance/confidence/challenges 正确解析 |
| `test_structure_extraction_fallback` | 提取调用超时或返回无效 JSON，验证 fallback 默认值 |
| `test_stream_interruption` | `chat_stream()` 中途抛异常，验证部分 argument + `(发言中断)` 标记 |
| `test_judge_streaming` | mock judge `chat_stream()`，验证 `judge_token` 事件产出 + `judge_verdict` 完整裁决 |
| `test_token_batching` | 验证 token 按 5 个一批或遇标点 flush 的逻辑 |
| `test_data_request_events` | mock DataFetcher，验证 `data_request_start`/`data_request_done`/`data_batch_complete` 事件逐个产出，含正确的 engine/action/duration_ms |
| `test_data_request_failure` | mock DataFetcher 部分请求失败，验证 `data_request_done` status="failed" + `data_batch_complete` 统计正确 |

### 4.2 集成测试

| 测试 | 验证点 |
|------|--------|
| `test_debate_sse_token_events` | POST `/api/v1/debate`，验证 SSE 流包含 `debate_token` 和 `debate_entry_complete`，顺序正确 |
| `test_mcp_http_transport` | 启动 MCP HTTP server，HTTP 调用 `start_debate`，验证 notification 推送和最终返回值 |

### 4.3 现有测试兼容

- debate 相关 mock 从 `chat()` 返回值改为 `chat_stream()` async generator
- `test_debate_e2e.py` 的 3 个测试适配新事件类型

## 影响范围

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `engine/llm/providers.py` | Bug 修复 | `_get_base_url` → `self.config.base_url.rstrip('/')` |
| `engine/agent/debate.py` | 重构 | speak_stream() + extract_structure() + judge 流式化 + 数据请求逐个事件化 |
| `engine/agent/personas.py` | 修改 | 辩论 prompt 改为纯自然语言输出 |
| `engine/mcpserver/__main__.py` | 重构 | `server.run(transport="streamable-http")` |
| `engine/mcpserver/server.py` | 修改 | start_debate 改 async def + ctx: Context |
| `engine/mcpserver/tools.py` | 重构 | 新增 start_debate_async() + ctx.log() 推送 |
| `engine/api/routes/debate.py` | 适配 | SSE 事件类型更新 |
| `engine/pyproject.toml` | 修改 | `mcp>=1.26.0` |
| `.mcp.json` | 配置 | stockterrain → HTTP url，保留 memory |
| `engine/tests/agent/test_debate_e2e.py` | 适配 | mock 和断言更新 |
| `engine/tests/agent/test_speak_stream.py` | 新增 | 流式 speak 单元测试 |
| `engine/tests/mcpserver/test_http_transport.py` | 新增 | MCP HTTP transport 集成测试 |
