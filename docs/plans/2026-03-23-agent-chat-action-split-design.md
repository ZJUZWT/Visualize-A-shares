# Agent Chat Action Split Design

> 编写日期：2026-03-23
> 范围：把 `/agent` 左侧聊天里的策略卡片一次性补齐为“采纳 / 忽略 / 收藏”三条独立能力，并打通真实虚拟组合写路径。

---

## 1. 背景

当前左侧策略卡片已经能从聊天消息里解析结构化交易计划，但动作语义仍停留在旧的 memo 流：

- `收藏` 写入 `strategy_memos`
- `忽略` 也借用了 memo 状态
- 并没有真正调用已有的 `/adopt-strategy` / `/reject-strategy`

这导致主界面的核心闭环还没成立：

- Agent 能提建议
- 用户能看到策略卡片
- 但“采纳后进入虚拟持仓 / 交易 / 策略”没有在主界面落地

同时，用户已经明确：

- `main agent` 自己维护的交易策略，和用户收藏到备忘录的策略，不是一个东西
- 左侧卡片需要同时支持 `采纳`、`忽略`、`收藏`

---

## 2. 目标

本批次一次性完成以下闭环：

1. 聊天策略卡片支持 `采纳`
2. 聊天策略卡片支持 `忽略`
3. 聊天策略卡片继续支持 `收藏到备忘录`
4. `采纳` 真实写入计划、交易、持仓策略
5. `忽略` 真实写入策略否决记录和 memory feedback
6. UI 能稳定回填“执行状态”和“备忘状态”

---

## 3. 非目标

本批次不做：

- 中栏 Strategy Brain 的整合改版
- 右栏持仓卡片的 richer 分组展示
- 备忘录面板的信息结构升级
- 新增复杂弹窗表单或多步确认流

---

## 4. 方案

采用“两条状态流并存”的方案，不再混用 memo 状态表示执行结果：

- 执行动作流：`/api/v1/agent/adopt-strategy`、`/api/v1/agent/reject-strategy`、`/api/v1/agent/strategy-actions`
- 备忘录流：`/api/v1/agent/strategy-memos`

同一张策略卡片允许同时存在两类结果：

- 执行结果：`已采纳` 或 `已忽略`
- 备忘结果：`已收藏`

这意味着一条策略可能出现以下状态：

- 仅收藏
- 已采纳
- 已忽略
- 已采纳且已收藏

但 `已采纳` 与 `已忽略` 仍然互斥，只属于同一条执行流。

---

## 5. 交互定义

策略卡片按钮调整为：

- 主按钮：`采纳`
- 次按钮：`忽略`
- 辅助按钮：`收藏到备忘录`

状态规则：

- 一旦已采纳或已忽略，执行按钮锁定，防止重复写组合
- 收藏按钮独立判断，已收藏后只锁定收藏动作
- `忽略` 继续支持填写可选备注，作为 reject reason
- 卡片顶部同时展示执行徽标和收藏徽标，避免用户误以为两者是同一件事

---

## 6. 数据流

前端对每张策略卡片维持同一个 lookup key：

- `message_id + strategy_key`

页面进入某个 session 后，同时拉两份数据：

- `fetchStrategyActions(sessionId)` 用于执行状态回填
- `fetchMemoActions(sessionId)` 用于备忘状态回填

卡片渲染时将两份状态合并，但不会把它们写回同一个后端表。

---

## 7. 代码落点

- `frontend/app/agent/types.ts`
  - 拆分执行动作类型和 memo 动作类型
- `frontend/app/agent/components/AgentStrategyActionCard.tsx`
  - 增加三按钮布局与双状态展示
- `frontend/app/agent/components/AgentChatMessage.tsx`
  - 向卡片传递 execution + memo 两套状态
- `frontend/app/agent/components/AgentChatPanel.tsx`
  - props 改名，避免继续把执行动作叫 memo action
- `frontend/app/agent/page.tsx`
  - 增加 `fetchStrategyActions`
  - 拆分 `handleStrategyExecutionAction` 与 `handleMemoSaveAction`
  - 会话切换时并行刷新两类状态
- `frontend/app/agent/lib/*`
  - 如有必要，抽出轻量状态映射 helper

后端本批次原则上不改合同，只复用已存在的：

- `backend/engine/agent/strategy_actions.py`
- `backend/engine/agent/strategy_action_routes.py`

---

## 8. 测试策略

采用前端 TDD，重点覆盖状态拆分后的行为：

- 采纳请求正确调用 `/adopt-strategy`
- 忽略请求正确调用 `/reject-strategy`
- 收藏请求继续调用 `/strategy-memos`
- 已采纳但未收藏时，卡片同时显示“已采纳”和可用收藏按钮
- 已收藏但未执行时，卡片显示“已收藏”，执行按钮仍可用
- 执行失败和收藏失败互不污染

后端继续复用现有 `strategy_actions` 单测，验证写路径稳定。
