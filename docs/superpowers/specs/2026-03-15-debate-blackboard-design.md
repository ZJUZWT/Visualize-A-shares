# 辩论黑板面板 设计文档

## 目标

在辩论页右侧新增黑板面板，实时展示专家搜索到的原始数据，让用户能够查阅信息来源，增强判断依据。同时重构辩论流程，使专家在每轮发言前先完成数据搜索。

---

## 后端流程重构

### 新辩论流程（每轮）

```
[公用数据] fetch_initial_data（在第一个 debate_round_start 之前执行）
→ initial_data_complete
→ debate_round_start (round=1)
→ [多头] request_data_for_round → fetch → blackboard_update × N
→ [空头] request_data_for_round → fetch → blackboard_update × N
→ [多头] speak_stream（纯发言，不含数据请求）
→ [空头] speak_stream
→ [散户] speak_stream
→ [主力] speak_stream
→ debate_round_start (round=2) ...
```

观察员（retail_investor、smart_money）不参与 `request_data_for_round`，其 `DEBATE_DATA_WHITELIST` 条目暂不使用。

### 新增函数

两个新函数均位于 `engine/agent/debate.py`。

**`fetch_initial_data(blackboard, data_fetcher)`**
- 在第一个 `debate_round_start` yield 之前执行
- 固定拉取三条公用数据，engine 字段如下：
  - `get_stock_info`（engine="data"）
  - `get_daily_history`（engine="data"，近30日）
  - `get_news`（engine="info"，近5条）
- 结果写入 `blackboard.facts`
- 每条数据先推送 `blackboard_update`（`status="pending"`），完成后再推送一次（`status="done"/"failed"`）
- 单条 fetch 失败时推送 `status="failed"` 并继续，不中断辩论
- 每条 fetch 超时：15秒
- 全部完成后推送 `initial_data_complete`
- `request_id` 格式：`public_{action}`（如 `public_get_stock_info`）

**`request_data_for_round(role, blackboard, llm)`**
- 每轮发言前，单独一次 LLM 调用，超时 15 秒
- System prompt：告知角色当前辩论状态，要求只输出 JSON 数组格式的数据请求列表，不输出任何发言
- 返回 `list[DataRequest]`，经白名单过滤后执行
- 每条请求先推送 `blackboard_update`（`status="pending"`），完成后推送（`status="done"/"failed"`）
- LLM 调用失败或超时时，跳过本轮数据请求，直接进入发言
- `request_id` 格式：`{role}_{action}_{round}`（如 `bull_expert_get_daily_history_1`）

### `speak_stream()` 改动（待迁移）

以下为目标状态，实现时需同步修改：

- `engine/agent/debate.py`：去掉 `extract_structure` 中 `data_requests` 字段的提取和处理
- `engine/agent/debate.py`：去掉 `_parse_debate_entry` 中 `【数据请求】` 块的解析
- `engine/agent/personas.py`：`_DEBATER_SYSTEM_TEMPLATE` 中去掉"【数据请求】"格式说明
- `DebateEntry.data_requests` 字段保留但始终为空列表

### `data_batch_complete` 事件

现有的 `data_batch_complete` 事件保留，但前端无需处理（store 中静默忽略）。

### 新增 SSE 事件

**`blackboard_update`**
```json
{
  "request_id": "public_get_stock_info",
  "source": "public",
  "engine": "data",
  "action": "get_stock_info",
  "title": "股票基本信息",
  "status": "pending" | "done" | "failed",
  "result_summary": "贵州茅台(600519)...",
  "round": 0
}
```
- `round=0` 表示公用初始数据（辩论轮次从 1 开始）
- `source` 取值：`"public" | "bull_expert" | "bear_expert"`
- 前端按 `request_id` upsert `blackboardItems`，即 `BlackboardItem.id = event.request_id`
- 窄屏下黑板面板可能被挤压，暂不处理响应式，已知限制

**`initial_data_complete`**
```json
{
  "total": 3,
  "success": 3,
  "failed": 0
}
```

---

## 前端改动

### 布局

`BullBearArena` 新增第四列：

```
[多头 w-52] [对话流 flex-1] [空头 w-52] [黑板 w-60]
```

### 新组件 `BlackboardPanel`

**文件：** `web/components/debate/BlackboardPanel.tsx`

**Props：**
```ts
interface BlackboardPanelProps {
  items: BlackboardItem[];
}
```

**展示逻辑：**
- 顶部标题"黑板"
- 竖向滚动列表，新数据追加到底部
- 每条默认折叠，显示：
  - 来源标签（公用=灰 / 多头=红 / 空头=绿）
  - 引擎图标（data/quant/info 用不同图标）
  - action 的中文 title
  - 状态（pending 转圈 / done ✓ / failed ✗）
- 点击展开显示 `result_summary`

### Store 改动

**新增类型：**
```ts
interface BlackboardItem {
  id: string;
  source: "public" | "bull_expert" | "bear_expert";
  engine: string;
  action: string;
  title: string;
  status: "pending" | "done" | "failed";
  result_summary?: string;
  round: number;
}
```

**新增 state 字段：**
```ts
blackboardItems: BlackboardItem[];
```

**新增 SSE 处理：**
- `blackboard_update`：追加或更新 `blackboardItems`
- `initial_data_complete`：可选，用于 UI 状态提示

**`reset()` 清空 `blackboardItems`**

### `BullBearArena` 改动

- 接收 `blackboardItems` prop
- 渲染 `BlackboardPanel`

### `DebatePage` 改动

- 从 store 取 `blackboardItems`，传给 `BullBearArena`

---

## Action 中文 title 映射

```ts
const ACTION_TITLE: Record<string, string> = {
  get_stock_info: "股票基本信息",
  get_daily_history: "日线行情",
  get_news: "最新新闻",
  get_announcements: "公告",
  get_factor_scores: "因子评分",
  get_technical_indicators: "技术指标",
  get_money_flow: "资金流向",
  get_northbound_holding: "北向持仓",
  get_margin_balance: "融资融券",
  get_turnover_rate: "换手率",
  get_cluster_for_stock: "聚类分析",
  get_financials: "财务数据",
  get_restrict_stock_unlock: "限售解禁",
  get_signal_history: "信号历史",
};
```

---

## 不在本次范围内

- Worker 分析师（fundamental/info/quant）流水线接入辩论
- 黑板数据的持久化展示（回放模式暂不展示黑板）
- 黑板数据的搜索/过滤功能
