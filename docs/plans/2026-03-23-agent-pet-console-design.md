# Agent Pet Console Design

> 编写日期：2026-03-23
> 范围：把现有 `/agent` 页面升级为 Main Agent 的宠物化主控台，支持 `宠物 / 训练 / 模拟盘 / 回测` 四个主页签，并让用户能在前台直接触发训练闭环。

---

## 1. 背景

当前 `/agent` 页面已经具备很多真实能力：

- Main Agent 聊天
- 策略脑摘要
- 执行账本 / 收益曲线 / 历史回放
- review / memory / reflection / strategy history

但它目前更像一组功能面板的堆叠，而不是一个“可培养、可观察、可派出去打仗”的主控台。

用户希望：

- 继续使用新的 main agent 页面
- 能在这个页面里看见整个 agent 培养过程
- 主界面更像电子宠物
- 聊天在右半屏
- 左上是主舞台
- 左下是策略区
- 训练 / 模拟盘 / 回测 用主页签分舱

---

## 2. 目标

本批次交付一个最小可体验版：

1. `/agent` 升级为四个主页签：
   - `宠物`
   - `训练`
   - `模拟盘`
   - `回测`
2. `宠物` 页完成主舞台布局：
   - 右半屏聊天
   - 左上像素电子宠物
   - 左下策略区
3. `训练` 页可直接触发后端训练闭环：
   - demo suite
   - smoke mode
4. `模拟盘` / `回测` 先复用现有账本、收益曲线、历史回放和 backtest 结果能力

---

## 3. 非目标

本批次不做：

- 完整角色美术资源系统
- 高复杂动画状态机
- 多 agent 宠物并列养成
- 完整成就系统 / 道具系统
- 训练页的复杂批量实验管理

第一版重点是“真能用”和“足够像一个活着的 agent”。

---

## 4. 方案对比

### 方案 A：新开一个独立 `/agent/lab` 页面

优点：

- 不污染现有页面

缺点：

- 用户要在两个 main agent 页面之间切换
- 体验割裂

### 方案 B：直接在现有 `/agent` 页面外包一层主控结构

做法：

- 保留现有数据获取逻辑
- 新增顶层主页签
- 把现有聊天、策略脑、账本、回放、复盘面板重新编排

优点：

- 改动集中
- 最大化复用已有组件
- 更快做出可体验版

缺点：

- `page.tsx` 会进一步变胖，需要适度抽 view-model / 组件

本批次采用方案 B。

---

## 5. 核心设计

### 5.1 顶层主页签

新增四个主页签：

- `pet`
- `training`
- `battle`
- `backtest`

语义：

- `pet`：主舞台 + 对话 + 当前策略
- `training`：训练闭环和进化观察
- `battle`：模拟盘账户与执行
- `backtest`：历史回测与日级过程

### 5.2 `pet` 页布局

布局固定为：

- 右半屏：聊天区
- 左上：主舞台
- 左下：策略区

主舞台内容：

- 像素风电子宠物
- 当前状态标签
- 一句人格化状态描述
- 最近一次动作
- 当前是否在训练 / 出战 / 回撤

策略区内容：

- 当前 market view / position level
- 最近一轮策略脑摘要
- 风险提示
- 最近训练结果摘要

### 5.3 宠物状态映射

第一版状态只保留五个：

- `idle`
- `thinking`
- `training`
- `battle`
- `drawdown`

状态来源：

- 当前 active run 状态
- 是否存在持仓 / pending plans
- 账户收益状态
- 最近训练结果

所有状态都由真实数据映射，不做纯装饰性的假数值系统。

### 5.4 `training` 页

训练页提供两个主入口：

- `Run Training Suite`
- `Run Smoke`

背后调用统一 suite：

- 默认模式：业务训练验证
- `smoke_mode=true`：工程 smoke 验收

展示结果：

- `pass / warn / fail`
- verification run id
- backtest run id
- trade / review / memory 指标
- next actions

### 5.5 `battle` 页

先复用现有执行台账能力：

- account overview
- open positions
- pending plans
- recent trades
- equity timeline

这一页在概念上就是“派出去打仗”。

### 5.6 `backtest` 页

先复用现有右侧账本和回放能力，并补一个最小回测控制区：

- 输入日期
- 触发 backtest
- 读取 summary
- 展示 daily rows / replay

### 5.7 需要新增的 backend HTTP 接口

前端不能直接调 MCP，因此需要一条很薄的后端 route 暴露 suite：

- `POST /api/v1/agent/verification-suite/run`

请求参数：

- `scenario_id`
- `backtest_start_date`
- `backtest_end_date`
- `timeout_seconds`
- `execution_price_mode`
- `smoke_mode`

返回：

- 直接透传 suite JSON

这条 route 不新增业务逻辑，只复用已有 suite wrapper。

---

## 6. 测试策略

### 6.1 backend

新增 route 单测，验证：

- 默认模式可调用 suite
- `smoke_mode` 参数正确透传
- route 返回结构化 JSON

### 6.2 frontend

不引入新 UI 测试框架，沿用现有 `node:test` 模式。

抽一个纯前端 view-model，负责：

- 主页签视图状态
- 宠物状态映射
- 训练结果摘要映射

用 `node:test` 覆盖这些纯逻辑。

### 6.3 验证

最终至少验证：

- backend pytest 通过
- frontend `node --test` 通过
- `npm run build` 通过

---

## 7. 为什么这版够好

这版不是把 `/agent` 做成花哨 dashboard，而是把它变成：

- 你和 main agent 的交互入口
- 训练它的操作台
- 观察它演化的显微镜
- 派它去模拟盘和历史战场的控制室

同时改动仍然可控：

- 大部分现有组件继续复用
- 只新增一个薄 HTTP route
- 只新增少量 view-model 和宠物主舞台组件
