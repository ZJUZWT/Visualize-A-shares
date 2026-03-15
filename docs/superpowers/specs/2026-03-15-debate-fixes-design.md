# 辩论系统修复与增强 — 设计文档

**日期**: 2026-03-15
**状态**: 待实现

---

## 问题概述

三个独立问题导致辩论系统无法正常工作：

1. **专家数据接口缺失** — AI 角色请求的 `get_financials`、`get_money_flow` 等 action 不在 `ACTION_DISPATCH` 中，被白名单过滤后专家只能用有限数据辩论
2. **`retail_sentiment_score` 类型错误** — `extract_structure()` prompt 描述不清，LLM 返回 dict 而非 float，导致 Pydantic 验证失败中断辩论
3. **前端无流式输出** — 后端推送 `debate_token`/`debate_entry_complete` 等新事件，前端 store 只处理旧的 `debate_entry`，完全对不上

---

## 修复方案

### 1. 扩展数据接口

#### 新增 actions

| action | 数据来源 | 说明 |
|---|---|---|
| `get_financials` | AKShare `stock_financial_analysis_indicator` | 最新一期财报：营收/净利润/ROE/负债率 |
| `get_money_flow` | AKShare `stock_individual_fund_flow` | 当日资金流向：主力净流入/大单/小单 |
| `get_northbound_holding` | AKShare `stock_hsgt_individual_em` | 北向持股：陆股通持股量/占比 |
| `get_margin_balance` | AKShare `stock_margin_detail_szse/sse` | 融资融券余额 |
| `get_turnover_rate` | DataEngine snapshot | 换手率（已有数据，补充到白名单） |
| `get_restrict_stock_unlock` | AKShare `stock_restricted_release_detail_em` | 限售股解禁计划 |

#### 实现位置

- `engine/agent/data_fetcher.py` — 新增 6 个方法直接挂在 `DataFetcher` 上，`ACTION_DISPATCH` 改为支持两种路由：
  1. 现有引擎路由（module + getter + method）
  2. self 路由：`action` 对应 `DataFetcher` 自身方法，dispatch 时用 `getattr(self, req.action)`
- `engine/agent/personas.py` — `DEBATE_DATA_WHITELIST` 各角色按需扩展

#### ACTION_DISPATCH 路由扩展

`fetch_by_request` 增加 self 路由分支：

```python
# 优先查 ACTION_DISPATCH（引擎路由）
if req.action in ACTION_DISPATCH:
    ...existing logic...
# 其次查 DataFetcher 自身方法（AKShare 直接调用）
elif hasattr(self, req.action):
    method = getattr(self, req.action)
    return await asyncio.to_thread(method, **req.params)
else:
    raise ValueError(f"不支持的 action: {req.action}")
```

#### get_turnover_rate 实现

`DataFetcher.get_turnover_rate(code)` — 从 DataEngine snapshot 中取 `turnover_rate` 字段：

```python
def get_turnover_rate(self, code: str) -> dict:
    from data_engine import get_data_engine
    snapshot = get_data_engine().get_snapshot()
    row = snapshot[snapshot["code"] == code]
    if row.empty:
        return {"error": f"未找到 {code}"}
    return {"code": code, "turnover_rate": float(row.iloc[0]["turnover_rate"])}
```

#### get_margin_balance 交易所路由

根据股票代码前缀判断交易所：
- `6xxxxx` → 上交所，用 `ak.stock_margin_detail_sse`
- `0xxxxx` / `3xxxxx` → 深交所，用 `ak.stock_margin_detail_szse`

#### get_financials AKShare 接口

优先用 `ak.stock_financial_analysis_indicator(symbol=code)`（无需 THS 订阅），返回最新一行的营收/净利润/ROE/资产负债率关键字段。

#### 数据返回长度限制

所有新接口返回的 dict 在 `fetch_by_request` 中统一截断：`str(result)[:300]`（与现有 `data_request_done` 的 200 字符对齐，略放宽到 300 以容纳财务数据）。

#### 白名单扩展

```python
"bull_expert": [
    "get_stock_info", "get_daily_history", "get_factor_scores",
    "get_news", "get_announcements", "get_technical_indicators",
    "get_cluster_for_stock", "get_financials", "get_turnover_rate",
],
"bear_expert": [
    "get_stock_info", "get_daily_history", "get_factor_scores",
    "get_news", "get_announcements", "get_technical_indicators",
    "get_cluster_for_stock", "get_financials", "get_restrict_stock_unlock",
    "get_margin_balance",
],
"retail_investor": [
    "get_news", "get_money_flow",
],
"smart_money": [
    "get_technical_indicators", "get_factor_scores",
    "get_money_flow", "get_northbound_holding", "get_margin_balance",
    "get_turnover_rate",
],
```

#### 数据获取策略

所有新接口均为异步，通过 `asyncio.to_thread` 包装同步 AKShare 调用。返回精简 dict，避免大量原始数据塞入 LLM 上下文（每个接口限制返回关键字段，字符串化后 ≤500 字符）。

---

### 2. 修复 retail_sentiment_score 类型错误

#### 根因

`extract_structure()` 的 prompt 中 `retail_sentiment_score` 只有 `null` 示例，无格式说明。LLM 误解为"对多只股票的情感评分字典"。

#### 修复

**prompt 补充说明**（`engine/agent/debate.py` `extract_structure()`）：

```python
"retail_sentiment_score": null,  # 仅 retail_investor 角色填写，其他角色必须为 null。
                                  # 格式：单一浮点数 -1.0 到 +1.0，+1 极度乐观，-1 极度悲观
```

**类型保护兜底**（`extract_structure()` 第 98 行，替换原有赋值）：

```python
# 原来（第 98 行）
"retail_sentiment_score": parsed.get("retail_sentiment_score"),
# 修复后
score = parsed.get("retail_sentiment_score")
"retail_sentiment_score": float(score) if isinstance(score, (int, float)) else None,
```

**顺带修复**：`_extract_judge_verdict` prompt 中 `debate_quality` 枚举值包含 `"moderate_disagreement"`，但 `JudgeVerdict` schema 和前端 `DebateQuality` 类型只允许 `"consensus" | "strong_disagreement" | "one_sided"`，需统一移除 `"moderate_disagreement"`。

---

### 3. 前端 SSE 事件对齐

#### 后端实际推送的事件

| 事件 | 数据 | 含义 |
|---|---|---|
| `debate_start` | `{debate_id, target, max_rounds, participants}` | 辩论开始 |
| `debate_round_start` | `{round, is_final}` | 新一轮 |
| `debate_token` | `{role, round, tokens, seq}` | 流式 token |
| `debate_entry_complete` | `DebateEntry` | 发言完整 |
| `data_request_start` | `{requested_by, engine, action, params, request_id}` | 开始拉数据 |
| `data_request_done` | `{request_id, action, status, result_summary, duration_ms}` | 数据就绪 |
| `data_batch_complete` | `{round, total, success, failed}` | 批次完成 |
| `debate_end` | `{reason, rounds_completed}` | 辩论结束 |
| `judge_token` | `{role, round, tokens, seq}` | 裁判流式 token |
| `judge_verdict` | `JudgeVerdict` | 裁判裁决 |
| `error` | `{message}` | 错误 |

#### 新增 TranscriptItem 类型

```typescript
// 新增
| { type: "streaming"; role: string; round: number; tokens: string }
| { type: "data_request"; id: string; requested_by: string; action: string;
    status: "pending" | "done" | "failed"; result_summary?: string; duration_ms?: number }
```

`streaming` item 的查找键为 `role + round` 组合（同一轮次同一角色唯一）。

#### store 事件处理补全

- `debate_token` → 用 `role + round` 查找 `streaming` item，存在则追加 tokens，不存在则插入新 streaming item
- `debate_entry_complete` → 将对应 `streaming` item（匹配 `role + round`）替换为 `entry` item；同时更新 roleState（辩论者）或 observerState + `_observerSpokenThisRound`（观察员），逻辑从废弃的 `debate_entry` handler 迁移过来
- `data_request_start` → transcript 插入 `data_request` item（status: pending，id = request_id）
- `data_request_done` → 用 `request_id` 找到对应 `data_request` item，更新 status/result_summary/duration_ms
- `judge_token` → 用 `role="judge" + round=null` 查找或创建 streaming item，追加 tokens
- `data_batch_complete` → 不需要 transcript 变更，可忽略
- 移除已废弃的 `debate_entry`、`data_fetching`、`data_ready` 处理

#### 前端组件

- `TranscriptFeed` — 新增渲染 `streaming` 气泡（打字机效果）和 `data_request` 卡片
- `SpeechBubble` — 支持 streaming 状态（显示光标动画）
- 新增 `DataRequestCard` 组件 — 显示数据请求状态（pending/done/failed）和结果摘要

---

## 文件变更清单

### 后端
- `engine/agent/data_fetcher.py` — 新增 6 个 action 方法 + ACTION_DISPATCH 扩展
- `engine/agent/personas.py` — 白名单扩展
- `engine/agent/debate.py` — prompt 修复 + 类型保护

### 前端
- `web/types/debate.ts` — 新增 TranscriptItem 类型
- `web/stores/useDebateStore.ts` — 补全 SSE 事件处理
- `web/components/debate/TranscriptFeed.tsx` — 渲染新类型
- `web/components/debate/SpeechBubble.tsx` — streaming 状态支持
- `web/components/debate/BullBearArena.tsx` — 传递新 props（如需）

---

## 不在本次范围内

- Worker 分析师初步判断的流式输出（当前 Blackboard.worker_verdicts 为空，Phase 2 实现）
- 辩论历史持久化优化
- 新数据接口的单元测试
