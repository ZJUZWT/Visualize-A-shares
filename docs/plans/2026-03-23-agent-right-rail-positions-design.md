# Agent Right Rail Position Cards Design

> 编写日期：2026-03-23
> 范围：把 `/agent` 右栏从“通用台账列表”升级为按 `holding_type` 分组的完整虚拟持仓卡视图，并补齐策略细节与执行状态灯所需 read model。

---

## 1. 背景

当前右栏已经具备：

- 账户概览
- 收益曲线
- 历史回放
- 当前持仓 / 计划 / 交易的基础列表

但 `TODO` 要求的关键部分仍未完成：

- 持仓按 `holding_type` 分组
- 每种持仓类型显示不同策略重点字段
- 展示当前策略执行状态灯

现有问题在于：

- `ledger overview` 的 `open_positions` 只有通用持仓字段
- 策略细节还藏在 `position_strategies`
- 前端如果逐持仓请求 strategy，会形成碎片化、多请求、慢交互

因此本批次采用一次性扩展 `ledger overview` 的方案。

---

## 2. 目标

本批次一次性完成：

1. 扩展 `ledger overview` 的 `open_positions` read model
2. 为每个 open position 注入最新策略 `latest_strategy`
3. 提供一个前端可直接消费的 `status_signal`
4. 右栏按 `holding_type` 分组展示 position cards
5. 卡片展示通用信息 + 不同持仓类型的重点字段
6. 保留现有账户概览、收益曲线、历史回放，不回退已有能力

---

## 3. 非目标

本批次不做：

- 新增独立 positions-with-strategy 接口
- 做T 全量专属交易逻辑后端建模扩展
- 饼图 / 复杂图表库
- 前端可编辑持仓策略
- 右栏改成多 tab

---

## 4. 方案

采用 `ledger overview` 扩展方案：

- 后端在 `get_ledger_overview()` 内对每个 open position 查询最新 strategy
- 在 position read model 上附带：
  - `position_pct`
  - `latest_strategy`
  - `status_signal`

其中 `status_signal` 先采用轻量规则推导：

- `danger`
  - 未实现盈亏 <= -5%
  - 或当前价格代理值已逼近止损区
- `warning`
  - 未实现盈亏 >= +8% 但未有明确兑现动作
  - 或止盈 / 止损阈值接近
- `healthy`
  - 其余情况

由于 Phase 当前没有实时现价字段，状态灯先基于当前 read model 中可得数据和 strategy 阈值做保守推导，不引入新的行情依赖。

---

## 5. 数据结构

`open_positions[]` 每项新增：

- `position_pct`
  - 当前持仓市值 / 总持仓市值
- `latest_strategy`
  - 最新 version 的 strategy 摘要
- `status_signal`
  - `healthy | warning | danger`
- `status_reason`
  - 说明为什么打这个灯

`latest_strategy` 先保留当前表里已经稳定存在的字段：

- `id`
- `holding_type`
- `take_profit`
- `stop_loss`
- `reasoning`
- `details`
- `version`
- `source_run_id`
- `created_at`
- `updated_at`

前端再从 `details` 中按持仓类型提取定制字段。

---

## 6. 前端展示

右栏新增 richer 持仓卡区，按以下顺序分组：

- `long_term`
- `mid_term`
- `short_term`
- 其他未识别类型归入 `other`

### 6.1 通用卡片内容

- 代码 / 名称
- 持仓类型标签
- 成本
- 市值
- 浮盈亏金额 / 百分比
- 仓位占比
- 状态灯 + 状态说明

### 6.2 长线卡重点

优先从 `latest_strategy.details` 提取：

- `fundamental_anchor`
- `exit_condition`
- `rebalance_trigger`

### 6.3 中线卡重点

- `trend_indicator`
- `add_position_price`
- `half_exit_price`
- `target_catalyst`

### 6.4 短线卡重点

- `hold_days`
- `next_day_plan`
- `volume_condition`

### 6.5 做T / 其他

当前后端 position 还未完整支持 `day_trade`，因此本批次先做兼容展示：

- 若 details 含 `t_core_qty / t_buy_price / t_sell_price` 则展示
- 否则回退到通用策略信息

---

## 7. 代码落点

- `backend/engine/agent/service.py`
  - 扩展 `get_ledger_overview`
  - 新增 position strategy summary / status signal helper
- `tests/unit/test_agent_read_models.py`
  - 补 ledger overview enriched read model 测试
- `frontend/app/agent/types.ts`
  - 扩展 `LedgerPosition`
- `frontend/app/agent/lib/rightRailPositionViewModel.ts`
  - 新增分组和卡片字段提取 helper
- `frontend/app/agent/lib/rightRailPositionViewModel.test.ts`
  - 新增 TDD 测试
- `frontend/app/agent/components/ExecutionLedgerPanel.tsx`
  - 用 richer grouped cards 替换当前通用“当前持仓”列表

---

## 8. 测试策略

后端：

- ledger overview 返回 enriched `open_positions`
- 带 strategy 的持仓能返回 `latest_strategy`
- `position_pct` 计算正确
- `status_signal` 与 `status_reason` 存在且稳定

前端：

- 持仓按 `holding_type` 分组
- 不同持仓类型提取正确重点字段
- 没有 strategy 时回退到通用卡片
- 状态灯文案正确
