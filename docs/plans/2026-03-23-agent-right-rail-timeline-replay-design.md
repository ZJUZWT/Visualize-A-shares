# Agent Right Rail Timeline And Replay Design

> 编写日期：2026-03-23
> 范围：为 `/agent` 右栏补齐“收益曲线 + 历史回放”最小前端闭环，直接消费已经落地的 timeline backend API。

---

## 1. 背景

当前 `/agent` 页面右栏仍以 `ExecutionLedgerPanel` 为主，重点是：

- 账户概览
- 当前持仓
- 未完成计划
- 最新交易

这能展示“现在的账本”，但还不能展示：

- 账户是如何随时间变化的
- AI 在某一天到底知道什么、做了什么、后来发生了什么

后端已经新增：

- `GET /api/v1/agent/timeline/equity`
- `GET /api/v1/agent/timeline/replay`

所以当前前端缺的不是能力，而是把这两个读模型接到右栏，形成一个可直接验证流程的 UI。

---

## 2. 目标

本批次前端只做最小闭环：

1. 右栏保留现有账户概览
2. 新增收益曲线卡
3. 新增历史回放卡
4. 回放支持切换日期
5. 错误与空状态局部隔离，不影响整栏使用

---

## 3. 非目标

本批次不做：

- 专业图表库接入
- 多时间区间筛选
- hover 十字线 / tooltip 细节
- 拖拽联动时间轴
- `thinking_process` 全量展开
- 新的后端接口

换句话说，这次目标是“验证可用”，不是“分析终版”。

---

## 4. 方案对比

### 方案 A：继续把右栏做成纯列表

做法：

- 在现有 `ExecutionLedgerPanel` 里继续堆更多表格和文本

优点：

- 改动最小

缺点：

- 没有时间维度
- 历史回放体验差
- 无法直观看到账户演化

### 方案 B：右栏扩成三段式执行视图

做法：

- 顶部账户概览
- 中间收益曲线卡
- 底部历史回放卡

优点：

- 结构清晰
- 最小代价覆盖“现在 + 过程 + 单日回看”
- 与现有右栏信息架构兼容

缺点：

- `ExecutionLedgerPanel` 体积会变大一些

### 方案 C：单独新建右栏 tab

优点：

- 分离更彻底

缺点：

- 交互层级变深
- 对当前 demo 软件来说过度设计

本批次采用方案 B。

---

## 5. 核心设计

### 5.1 右栏结构

`ExecutionLedgerPanel` 扩成三块：

1. `Account Snapshot`
   - 保留当前账户概览卡
2. `Equity Timeline`
   - 展示两条线：
     - `mark_to_market`
     - `realized_only`
   - 追加最后一个点的差值摘要
3. `Historical Replay`
   - 日期选择器
   - 当日账户摘要
   - 当日持仓
   - 当日 trades / plans
   - `what_ai_knew`
   - `what_happened`

### 5.2 数据流

页面行为：

1. 继续加载 `ledger/overview`
2. `portfolioId` 就绪后，再并行加载：
   - `timeline/equity`
   - `timeline/replay`
3. 默认回放日期：
   - 优先 timeline 最后一天
   - timeline 为空时回退到今天
4. 用户切换日期时，只刷新 replay
5. 曲线与回放的错误分离显示

### 5.3 收益曲线表现

首批不用图表依赖，直接用轻量 SVG 折线：

- 只依赖浏览器原生 SVG
- 避免引入 recharts / nivo 等额外依赖
- 方便在测试中验证空态与数据态

展示字段：

- 横轴：日期
- 纵轴：总资产值
- 两条线颜色区分
- 右上角展示：
  - 最新 `mark_to_market`
  - 最新 `realized_only`
  - 差值（未实现盈亏影响）

### 5.4 历史回放表现

日期选择器：

- 使用 `input[type=date]`
- `min / max` 取自 timeline 首尾日期

内容结构：

1. `Account`
   - `cash_balance`
   - `total_asset_mark_to_market`
   - `total_asset_realized_only`
   - `realized_pnl`
   - `unrealized_pnl`
2. `Positions`
   - 代码、数量、成本、收盘价、市值、浮盈亏
3. `Actions`
   - 当日 trades
   - 当日 plans
4. `AI Context`
   - `trade_theses`
   - `plan_reasoning`
5. `Outcome`
   - `review_statuses`
   - `next_day_move_pct`

### 5.5 状态处理

每块都单独处理：

- `loading`
- `error`
- `empty`
- `ready`

避免一个接口失败导致整栏不可用。

### 5.6 类型与 normalize

前端需要补充两类类型：

- `AgentEquityTimeline`
- `AgentReplaySnapshot`

同时在 `page.tsx` 增加对应 normalize helper，保证：

- 缺字段时不崩
- 数字 / 字符串数字兼容
- 空数组有稳定默认值

---

## 6. 代码落点

首批涉及文件：

- `frontend/app/agent/types.ts`
  - 新增 timeline / replay 类型
- `frontend/app/agent/page.tsx`
  - 新增数据请求、默认日期、normalize、状态管理
- `frontend/app/agent/components/ExecutionLedgerPanel.tsx`
  - 扩展为概览 + 曲线 + 回放的三段式右栏
- `frontend/app/agent/*.test.tsx` 或现有测试文件
  - 覆盖 normalize 和关键渲染状态

不新建全局状态，不改页面总布局。

---

## 7. 测试策略

首批只做最小前端测试：

1. timeline normalize 正常处理空值和缺字段
2. replay normalize 正常处理空值和缺字段
3. `ExecutionLedgerPanel` 能渲染：
   - timeline 成功态
   - timeline 空态
   - replay 错误态
4. 默认日期逻辑正确：
   - 优先 timeline 最后一天
   - timeline 为空时不崩

不做视觉快照，不做复杂交互测试。

---

## 8. 后续扩展位

这批做完后，可以自然往下加：

- 曲线 hover 明细
- 点击曲线点自动同步 replay 日期
- 展开完整 `thinking_process`
- 多时间区间筛选

但这些都不应该阻塞当前“验证 AI 轮回闭环”的目标。
