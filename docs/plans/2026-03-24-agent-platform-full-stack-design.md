# Agent Platform Full-Stack Design

> 编写日期：2026-03-24
> 范围：补齐 Main Agent 平台侧剩余的三条主链路，统一完成 `Valuation Chain`、`Full Analysis Chain`、`Agent UX Chain`，让 `/agent` 从“可浏览的控制台”升级为“可显式发起深度分析、可回看分析结论、可读到真实市值”的完整工作台。

---

## 1. 背景

根目录 `TODO.md` 已经收尾，但当前系统仍存在三个真实缺口，直接影响 Main Agent 的实用性和可信度：

1. 组合估值口径仍不统一  
   在 [backend/engine/agent/service.py](/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/engine/agent/service.py) 中，`get_portfolio()` 与 `_build_position_read_model()` 仍以 `entry_price * qty` 估算持仓市值。这会让账户总资产、浮盈亏、仓位占比与真实行情脱节。

2. `full_analysis` 仍停留在 TODO  
   [backend/mcpserver/tools.py](/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/mcpserver/tools.py) 只有注释，没有真正的组合分析工具。外部 agent 或 MCP 客户端无法一次拿到“行情 + 量化 + 资讯 + 产业链”的结构化结论。

3. `/agent` 还没有显式的深度分析工作流  
   当前 [backend/engine/agent/chat.py](/Users/swannzhang/Workspace/AIProjects/A_Claude/backend/engine/agent/chat.py) 的默认 runtime 仅回显文本；[frontend/app/agent/page.tsx](/Users/swannzhang/Workspace/AIProjects/A_Claude/frontend/app/agent/page.tsx) 虽然有 session、watchlist、ledger、timeline、run panels，但缺少“点一个标的就做深度分析”的一等入口，多个区域仍依赖“接口暂不可用 / 尚未就绪”式降级提示。

用户已经明确本轮目标不是继续拆小模块，而是：

- 后端和前端一起补齐
- 不做定时任务
- 强化“两个 AI / 多链路产生不同观点”的深度问答体验
- 保留 SSE / 渐进式体验
- 优先做长期主义的平台能力，而不是局部修补

---

## 2. 目标

本模块完成后，需要同时满足以下结果：

1. 组合、台账、持仓、回放使用真实或可解释的价格口径，而不是固定成本价
2. 所有估值结果都带上来源与降级状态，至少区分：
   - `realtime`
   - `snapshot`
   - `close_history`
   - `cost_fallback`
3. `full_analysis(code)` 成为真正可调用的 MCP tool，返回结构化结果，并允许部分成功
4. `/agent` 页面提供显式“深度分析”入口，而不是只能靠聊天隐式触发
5. 分析结果能同时进入：
   - chat message stream
   - runtime / strategy / memo 上下文
   - 右侧或对应工作区中的 latest analysis summary
6. 前端不再用泛化的“暂不可用”掩盖已具备的数据，而是展示精确的降级状态与来源说明

---

## 3. 非目标

本轮不做：

- 重写 Main Agent 的交易决策主循环
- 新增定时任务或后台批处理
- 把所有分析都接入真正的 LLM 辩论链
- 重构整个 `/agent` 页面布局
- 重写 timeline/replay 的历史重放算法

本轮是“补齐平台能力 + 显式接入 UI”，不是再造一个新 agent。

---

## 4. 现状判断

### 4.1 已有能力

当前系统其实已经有几块可直接复用的基础：

- `timeline/replay` 已经会根据历史日线重建 `mark_to_market` 与 `realized_only`
- `DataEngine` 已有：
  - `/api/v1/data/snapshot/{code}`
  - `/api/v1/data/daily/{code}`
  - `get_asset_quote()`
- `InfoEngine` 已有：
  - `get_news`
  - `get_announcements`
  - `assess_event_impact`
- `IndustryEngine` 已有：
  - `query_industry_cognition`
  - `query_capital_structure`
- `/agent` 前端已有：
  - 持久化 chat session
  - watchlist
  - ledger/timeline/replay panels
  - 最近 brain run / analysis_results 展示

### 4.2 当前真正的问题

真正缺的不是“基础数据能力”，而是“共享的平台组合层”：

1. 估值读取没有统一 resolver
2. 深度分析没有共享聚合器
3. agent chat、latest analysis、ledger 三条 UI 链路没有共用同一份分析/估值读模型

因此本轮应该采用“平台先行，前端跟进”，而不是分别在 MCP、service、page 里做三套不同实现。

---

## 5. 方案对比

### 方案 A：只修 `get_portfolio()` 和页面文案

优点：

- 最快
- 风险最低

缺点：

- `full_analysis` 仍不存在
- `/agent` 仍没有显式深度分析入口
- 估值、分析、UI 继续三套口径

不采用。

### 方案 B：共享平台层先落地，再把 MCP 与 `/agent` 都接到它上面

优点：

- 满足长期主义目标
- MCP 与 `/agent` 共用同一个分析结构
- 降级状态、数据来源、UI 摘要都可以统一

缺点：

- 需要补 schema、读模型和前端类型
- 文档与测试都要同步补全

推荐采用。

### 方案 C：把深度分析完全塞进 chat runtime

优点：

- 似乎可以少一个新接口

缺点：

- 分析动作会继续隐藏在聊天里
- latest analysis summary 与独立右侧面板没有稳定读模型
- MCP tool 与 `/agent` 仍然难以复用

不采用。

---

## 6. 核心设计

### 6.1 Valuation Chain

新增共享估值解析层，核心职责是把“持仓记录”转换为“当前可解释的估值结果”。

建议新增：

- `backend/engine/agent/valuation.py`

核心输出结构：

```python
{
    "latest_price": 112.0,
    "market_value": 11200.0,
    "unrealized_pnl": 1200.0,
    "unrealized_pnl_pct": 12.0,
    "valuation_source": "snapshot",
    "valuation_as_of": "2026-03-24",
    "degraded": False,
    "fallback_reason": None,
}
```

价格优先级：

1. `realtime`
   仅在明确可取到实时 quote 时使用
2. `snapshot`
   使用本地或接口可读到的最新快照价
3. `close_history`
   使用最近一个可用收盘价
4. `cost_fallback`
   无行情数据时退回持仓成本口径

接入位置：

- `get_portfolio()`
- `_build_position_read_model()`
- `get_ledger_overview()`
- `get_replay_snapshot()`

说明：

- `get_equity_timeline()` 和 `get_replay_snapshot()` 现有历史重建逻辑不需要推翻
- 它们已经是 mark-to-market，只需要把 `pricing_context` / `price_source` 明确暴露出去

### 6.2 Full Analysis Chain

新增共享组合分析聚合器，建议放在：

- `backend/engine/runtime/full_analysis.py`

它不直接依赖某个页面，也不直接依赖 MCP transport，而是做纯聚合：

- `snapshot / profile / daily history`
- `technical indicators`
- `factor scores`
- `news`
- `announcements`
- `industry cognition`
- `capital structure`

统一结果结构：

```python
{
    "stock_code": "600519",
    "stock_name": "贵州茅台",
    "status": "partial",
    "summary_blocks": [
        {"id": "market", "title": "行情与估值", "tone": "neutral", "summary": "..."},
        {"id": "quant", "title": "技术与因子", "tone": "positive", "summary": "..."},
        {"id": "info", "title": "资讯与公告", "tone": "neutral", "summary": "..."},
        {"id": "industry", "title": "产业链与资金", "tone": "positive", "summary": "..."},
    ],
    "sections": {
        "market": {"status": "ok", "source": "snapshot", "payload": {...}},
        "quant": {"status": "ok", "source": "quant", "payload": {...}},
        "info": {"status": "error", "source": "info", "error": "..."},
        "industry": {"status": "degraded", "source": "industry", "payload": {...}},
    },
}
```

关键原则：

- 部分成功允许返回 `partial`
- 每个 section 单独携带 `status/source/error`
- 对 UI 友好的 `summary_blocks` 与对程序友好的 `sections/payload` 同时存在

### 6.3 Agent Analysis Persistence

为了让分析结果同时出现在 chat、右侧摘要和 runtime context 中，需要新增持久化读模型。

建议新增表：

- `agent.analysis_records`

建议字段：

```sql
id
portfolio_id
stock_code
stock_name
trigger_source
source_session_id
source_message_id
summary_blocks JSON
structured_payload JSON
status
created_at
updated_at
```

这样可以支持：

- latest analysis summary
- session/message 级回溯
- runtime context 注入“最近一次深度分析”
- 后续策略 memo 或 strategy action 关联来源

### 6.4 Agent UX Chain

前端不走“聊天里暗号触发”的隐式路线，而是加显式入口：

1. `watchlist` 行项目增加“深度分析”动作
2. 当前持仓/右侧台账中也提供同类入口
3. chat composer 区域增加显式分析按钮或快捷触发
4. 触发后走独立 analysis SSE，而不是普通文本 chat
5. 完成后：
   - 写入 `analysis_records`
   - 插入一条 assistant message
   - 在右侧显示 latest analysis summary

建议新增前端卡片：

- `AgentAnalysisCard`

它负责显示：

- 标的代码/名称
- 分析状态
- 核心结论摘要块
- 各 section 的来源 / 降级说明
- 可选展开原始 payload

### 6.5 Chat 与 Analysis 的关系

本轮不把深度分析完全并入普通 chat 请求。

采用：

- 普通自然语言继续走 `/api/v1/agent/chat`
- 显式深度分析走 `/api/v1/agent/analysis/deep`

但二者共享：

- session_id / message stream
- persisted assistant message
- runtime context 注入最近分析结果

这样既保留显式入口，也不割裂会话历史。

### 6.6 降级与错误策略

#### 估值降级

- 实时/快照成功：显示最新价、来源、时间
- 只有历史收盘：显示 `close_history`
- 行情全无：显示 `cost_fallback`

前端文案应精确到来源，不再使用“暂不可用”笼统提示。

#### Full Analysis 降级

- 单 section 失败不影响总体返回
- `status` 可为：
  - `completed`
  - `partial`
  - `failed`
- 每个 block 显示独立状态：
  - `ok`
  - `degraded`
  - `error`

#### UI 降级

- 无 latest analysis：显示“尚未发起深度分析”
- 有 partial 结果：正常展示已完成 blocks，并单独提示缺失来源
- 只有 fallback 估值：仍显示总资产，但标注成本口径

---

## 7. 页面改动范围

### 7.1 `AgentChatPanel`

补显式分析入口：

- watchlist 项上的“分析”
- 可能的 quick action 区域

### 7.2 `AgentChatMessage`

增加分析消息卡片渲染：

- 普通文本
- 策略计划卡
- 深度分析卡

### 7.3 `ExecutionLedgerPanel`

补齐：

- `latest_price`
- `valuation_source`
- `valuation_as_of`
- 更精确的 mark-to-market / realized_only 对照说明

### 7.4 `page.tsx`

新增：

- 分析请求状态管理
- latest analysis 拉取与归一化
- SSE 事件处理
- 将分析结果同步到 chat entries + right rail summary

---

## 8. 测试策略

### 8.1 Backend

- 单元测试估值优先级与降级路径
- 读模型测试 portfolio / ledger / replay 的新字段
- 分析聚合器测试 partial success
- MCP wrapper / server registration 测试
- chat / analysis route contract 测试

### 8.2 Frontend

- view model 单测：
  - valuation normalization
  - analysis record normalization
  - latest analysis summary
- `/agent` 组件测试：
  - 分析按钮状态
  - 分析卡渲染
  - fallback 文案精确性

### 8.3 Smoke

扩展 Playwright mock：

- mock `GET /api/v1/agent/analysis/latest`
- mock `POST /api/v1/agent/analysis/deep`

至少覆盖：

1. `/agent` 页面正常打开
2. 点击显式深度分析入口后不会报 runtime error
3. 分析卡片与 latest analysis summary 能出现

---

## 9. 实施顺序

推荐顺序：

1. 先做估值 resolver 与读模型
2. 再做 shared full analysis aggregator
3. 再做 agent analysis persistence + route
4. 然后补 MCP tool 包装
5. 最后接前端消息卡、右侧摘要与 smoke

原因：

- 估值与分析结构是平台层
- `/agent` UI 一旦先写，很容易再次退回 mock/fallback 驱动
- MCP 和 `/agent` 共用同一套结构后，后续再扩展“两个 AI 的不同观点”也更稳

---

## 10. 验收标准

完成后应满足：

1. `get_portfolio()` / `get_ledger_overview()` 返回真实或可解释的估值口径
2. `/agent` 台账面板显示估值来源
3. `full_analysis` 出现在 MCP tool 列表里，且能返回结构化结果
4. `/agent` 能显式发起深度分析，不依赖手输 prompt
5. 分析结果进入：
   - chat history
   - latest analysis summary
   - runtime context
6. 前端没有新的 runtime error
7. Backend 单测、frontend unit、frontend smoke 全部通过
