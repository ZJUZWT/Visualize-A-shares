# Phase 1B-1: 交易计划备忘录 — 设计规格

> **目标**：让专家对话中 AI 给出的交易建议可以一键收藏为结构化的交易计划，用户第二天不会忘。
> 纯增量功能，不改动现有对话逻辑，不涉及 Main Agent 自主交易。

---

## 1. 架构概览

```
现有专家对话 (/expert)
    │
    │ AI 回复中包含 【交易计划】...【/交易计划】
    │
    ▼
前端解析 → 渲染为交易计划卡片 → 用户点"收藏"
    │
    │ POST /api/v1/agent/plans
    │
    ▼
agent.duckdb → trade_plans 表
    │
    │ GET /api/v1/agent/plans
    │
    ▼
前端 /plans 页签 → 查看、管理、更新状态
```

**新增/修改点**：
- 后端：`trade_plans` 表（复用 `agent.duckdb`）+ 5 个 CRUD API
- 后端：专家对话 system prompt 追加交易计划格式约定
- 前端：对话中解析交易计划块 → 卡片渲染 + 收藏按钮
- 前端：`/plans` 备忘页签

---

## 2. 数据模型

### 2.1 trade_plans 表

```sql
CREATE TABLE IF NOT EXISTS agent.trade_plans (
    id VARCHAR PRIMARY KEY,
    stock_code VARCHAR NOT NULL,
    stock_name VARCHAR NOT NULL,
    current_price DOUBLE,               -- 建议时的现价
    direction VARCHAR NOT NULL,         -- buy/sell

    -- 进场策略
    entry_price DOUBLE,                 -- 建议买入/卖出价
    entry_method TEXT,                  -- "分两批，1750先买半仓，1720补另一半"
    position_pct DOUBLE,               -- 建议仓位比例 0.1 = 10%

    -- 离场策略
    take_profit DOUBLE,                 -- 止盈价
    take_profit_method TEXT,            -- "到2000先减半，2100清仓"
    stop_loss DOUBLE,                   -- 止损价
    stop_loss_method TEXT,              -- "跌破1650一次性清仓"

    -- 理由
    reasoning TEXT NOT NULL,            -- 交易理由
    risk_note TEXT,                     -- 风险提示
    invalidation TEXT,                  -- 失效条件

    -- 时效 & 状态
    valid_until DATE,                   -- 有效期
    status VARCHAR DEFAULT 'pending',   -- pending/executing/completed/expired/ignored

    -- 来源
    source_type VARCHAR DEFAULT 'expert', -- expert/agent/manual
    source_conversation_id VARCHAR,      -- 来源对话ID

    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);
```

**状态流转**：
```
pending → executing → completed
                   → expired（有效期过了）
                   → ignored（用户主动放弃）
```

### 2.2 Pydantic 模型

```python
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
    """创建交易计划的 API 入参"""
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
    source_type: str = "expert"
    source_conversation_id: str | None = None

class TradePlanUpdate(BaseModel):
    """更新交易计划状态"""
    status: Literal["pending", "executing", "completed", "expired", "ignored"] | None = None
```

---

## 3. API 端点

注册路径：`/api/v1/agent/plans`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/plans` | 创建交易计划（前端点"收藏"时调用） |
| GET | `/plans` | 列表，支持 `?status=pending&stock_code=600519` |
| GET | `/plans/{id}` | 单个计划详情 |
| PATCH | `/plans/{id}` | 更新状态或字段 |
| DELETE | `/plans/{id}` | 删除计划 |

**错误响应**：
- 404: 计划不存在
- 400: 参数校验失败

---

## 4. Prompt 模板约定

在专家对话的 system prompt 末尾追加以下规则：

```
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
```

**约定**：
- `【交易计划】` 和 `【/交易计划】` 是开闭标签，前端据此解析
- 标的、方向、建议价格、止损价格、理由为必填字段
- 其余字段可选，AI 根据情况填写
- AI 只在有足够信心给出完整方案时才使用此格式

**Prompt 注入位置**：修改专家对话的 system prompt 构建逻辑，在末尾追加此段。具体文件需要在实现时确认（可能是 `backend/engine/expert/` 或 `backend/llm/` 下的 prompt 模板）。

---

## 5. 前端：对话中识别 + 卡片渲染

### 5.1 解析逻辑

在渲染 AI 回复的 Markdown 时，检测 `【交易计划】...【/交易计划】` 块：

```typescript
// 伪代码
const PLAN_REGEX = /【交易计划】([\s\S]*?)【\/交易计划】/g;

function parseTradePlan(block: string): TradePlan {
    const lines = block.trim().split('\n');
    const plan: Record<string, string> = {};
    for (const line of lines) {
        const match = line.match(/^(.+?)：(.+)$/);
        if (match) {
            plan[match[1].trim()] = match[2].trim();
        }
    }
    // 映射中文 key → API 字段
    return {
        stock_code: plan['标的']?.split(' ')[0],
        stock_name: plan['标的']?.split(' ').slice(1).join(' '),
        current_price: parseFloat(plan['当前价格']),
        direction: plan['方向'] === '买入' ? 'buy' : 'sell',
        entry_price: parseFloat(plan['建议价格']),
        entry_method: plan['买入方式'],
        position_pct: parseFloat(plan['仓位建议']) / 100,
        take_profit: parseFloat(plan['止盈目标']),
        take_profit_method: plan['止盈方式'],
        stop_loss: parseFloat(plan['止损价格']),
        stop_loss_method: plan['止损方式'],
        reasoning: plan['理由'],
        risk_note: plan['风险提示'],
        invalidation: plan['失效条件'],
        valid_until: plan['有效期'],
    };
}
```

### 5.2 卡片组件 `TradePlanCard`

- 顶部：股票代码+名称 + 方向标签（买入绿色 / 卖出红色）
- 中间分三区：
  - 进场策略：建议价格、买入方式、仓位
  - 离场策略：止盈目标+方式、止损价格+方式
  - 理由：核心逻辑、风险提示、失效条件
- 底部：有效期 + "收藏到备忘录"按钮
- 点击收藏 → POST `/api/v1/agent/plans`，按钮变为"已收藏 ✓"

### 5.3 流式兼容

AI 回复是 SSE 流式的，`【交易计划】` 块可能分多个 token 到达。处理方式：
- 流式过程中检测到 `【交易计划】` 开始标签后，暂存后续内容
- 检测到 `【/交易计划】` 闭合标签后，一次性解析并渲染卡片
- 闭合前显示为普通文本（用户能看到内容逐步出现）

---

## 6. 前端：备忘页签 `/plans`

### 6.1 路由与导航

- 路由：`/plans`
- 导航栏新增入口：📋 图标 + "计划"文字

### 6.2 页面布局

- 顶部：状态筛选 tabs — 全部 | 待执行 | 执行中 | 已完成 | 已过期 | 已忽略
- 搜索栏：按股票代码/名称搜索
- 主体：计划卡片列表
  - 复用 `TradePlanCard` 组件样式
  - 额外显示：状态标签（颜色区分）、创建时间、有效期
  - 状态切换：下拉菜单或按钮组，可切换 pending → executing → completed/ignored
  - 点击卡片展开完整详情

### 6.3 过期处理

- 不做后端定时任务
- 前端渲染时判断 `valid_until < today` 且 `status == 'pending'`，显示为"已过期"样式
- 用户也可手动标记过期

---

## 7. 与现有系统的集成

- **AgentDB**：复用 Phase 1A 的 `AgentDB` 单例，在 `_init_tables()` 中新增 `trade_plans` 表
- **API 路由**：在 `routes.py` 中新增 plans 相关端点，挂载在同一个 agent router 下
- **专家对话 Prompt**：找到专家对话的 system prompt 构建位置，追加交易计划格式约定
- **前端对话组件**：在现有的消息渲染组件中增加交易计划块的检测和卡片渲染

---

## 8. 不在 Phase 1B-1 范围内

| 内容 | 推迟到 | 理由 |
|------|--------|------|
| Main Agent 自主交易 | Phase 1B-2 | 需要 Agent Brain |
| 虚拟持仓联动 | Phase 1B-2 | 备忘录和虚拟持仓是独立的 |
| 自动过期后端任务 | 后续 | 前端判断足够 |
| 计划执行后自动复盘 | Phase 1D | 需要复盘系统 |
| 多用户隔离 | 后续 | 当前单用户 |
