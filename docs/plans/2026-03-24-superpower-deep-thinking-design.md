# Superpower Deep Thinking Design

> 编写日期：2026-03-24
> 范围：只覆盖 `expert` 对话链路中的 `rag`（投资顾问）与 `short_term`（短线专家），不影响定时任务、不改 Main Agent 主脑。

---

## 1. 背景

当前 `expert` 聊天链路已经具备：

- `think -> tool_call -> tool_result -> reply -> belief_update` 的流式阶段
- 前端 `ThinkingPanel` 的结构化思考面板
- `deepThink` 多轮补查能力

但它仍然缺三件用户明确想要的体验：

1. 在分析前先确认“你到底要我按什么角度回答”
2. 在分析中更明显地展示 AI 的拆题与推理摘要
3. 在给结论前先做一轮自我质疑，而不是只给单一路径答案

用户要的不是“更长的思维链”，而是更接近 `brainstorming` / `superpower` 的深度问答流程：

- 先理解问题
- 再给 A/B/C/D 选项确认方向
- 支持 `跳过，直接分析`
- 再进入深度分析
- 最后显式展示自我质疑

---

## 2. 目标

本模块完成后，`expert` 深度思考模式应满足：

1. 当用户开启深度思考时，`rag` 和 `short_term` 在正式分析前先进行一次 clarification
2. clarification 输出包括：
   - 用户问题理解摘要
   - 3-4 个可选分析方向
   - 1 个 `跳过，直接分析` 选项
3. 用户选择后，再进入原有 expert 分析链路
4. 思考面板可展示：
   - clarification 请求
   - reasoning 摘要
   - self critique
5. 最终回复正文仍然是自然语言，但思考面板中可以看到 AI 如何理解、如何拆题、如何质疑自己

---

## 3. 非目标

本轮不做：

- 定时任务 clarification
- Main Agent 主脑深思考模式
- 对所有引擎专家（`data/quant/info/industry`）单独增加 clarification
- 自由输入式 clarification 表单
- 多轮 clarification 往返
- 新的数据库表

本轮只做 expert chat 的“一次 clarification + 一次深入分析”。

---

## 4. 方案对比

### 方案 A：前端本地生成选项卡

优点：

- 实现快
- 不改后端主链路

缺点：

- 选项不是基于 persona 和上下文真实生成
- 无法写入思考链与会话记录
- 很容易变成死模板

不采用。

### 方案 B：单独增加 clarification API，再调用原 chat

流程：

1. 前端先 `POST /expert/clarify/{expert_type}`
2. 后端返回理解摘要 + 选项
3. 用户点选后，前端把选项内容拼进下一轮 `chat`

优点：

- 前后端状态清晰
- 不会让 `chat` SSE 在 clarification 阶段悬挂等待
- 与现有 session 写入模型兼容

缺点：

- 前端 store 要多一个待确认状态
- 需要定义 clarification 请求体与选择回填协议

推荐采用。

### 方案 C：把 clarification 内嵌到 SSE，等待用户再继续

优点：

- 看起来像一个完整长链路

缺点：

- SSE 会被用户交互中断，前端状态复杂
- 路由和会话写入逻辑更难维护
- 中途恢复生成的协议成本高

不采用。

---

## 5. 核心设计

### 5.1 模式入口

只有当以下条件同时满足时才触发 clarification：

- expert 类型为 `rag` 或 `short_term`
- `deep_think=true`
- 当前请求不是定时任务链路

否则保持现有聊天逻辑不变。

### 5.2 Clarification 数据结构

后端新增结构：

- `ClarificationOption`
  - `id`
  - `label`
  - `title`
  - `description`
  - `focus`
- `ClarificationOutput`
  - `should_clarify`
  - `question_summary`
  - `options`
  - `reasoning`
  - `skip_option`

其中：

- `label` 用于 `A/B/C/D`
- `skip_option` 固定为 `跳过，直接分析`
- `reasoning` 不直接放正文，进入 thinking 面板

### 5.3 Clarification API

新增：

- `POST /api/v1/expert/clarify/{expert_type}`

请求体：

- `message`
- `session_id`

返回：

- persona 化的理解摘要
- 3-4 个分析方向选项
- `skip` 选项

前端选择后，不单独调 `/expert/clarify/confirm`，而是直接将选择结果回填到下一次 `chat` 请求中：

- `clarification_selection`
  - `option_id`
  - `label`
  - `title`
  - `focus`
  - `skip`

这样可以避免额外确认接口，把状态收敛到一次 `clarify` + 一次 `chat`。

### 5.4 Chat 请求扩展

`ExpertChatRequest` 增加：

- `clarification_selection: ClarificationSelection | None = None`
- `use_clarification: bool = True`

解释：

- 首次发送深度消息时，前端先调 `clarify`
- 用户选定后再调 `chat`
- `chat` 内部将 selection 拼接为额外分析约束，影响 `_think`、`_reply_stream`、`_self_critique`

### 5.5 Thinking Out Loud 事件模型

新增 SSE 事件：

- `clarification_request`
- `reasoning_summary`
- `self_critique`

含义：

- `clarification_request`
  - 仅由 `/clarify` 返回 JSON，不走 SSE；但会在前端写入 thinking item
- `reasoning_summary`
  - 在 `recall_and_think()` 后发出
  - 内容来自 `ThinkOutput.reasoning`
- `self_critique`
  - 在 `reply_complete` 之前发出
  - 展示 AI 对结论的反证、适用条件和不确定性

换句话说，clarification 走普通 JSON API；thinking / critique 走 chat SSE。

### 5.6 Self-Critique 设计

后端新增 `SelfCritiqueOutput`：

- `summary`
- `risks`
- `missing_data`
- `counterpoints`
- `confidence_note`

触发时机：

1. 正常完成 think + tools 后
2. 在正式 reply 之前，调用一段轻量 critique prompt
3. 产出结构化 critique
4. 先发 `self_critique` 事件，再开始最终正文生成

要求：

- 不推翻主回答流程
- 只做“我可能错在哪、还缺什么、什么条件下结论失效”
- 若证据不足，可明确提示偏保守

### 5.7 Persona 差异

clarification 和 critique 也必须体现人格差异：

- 投资顾问：
  - clarification 更强调目标是“估值 / 风险收益比 / 仓位 / 观察清单”
  - self critique 更强调“安全边际不足、验证周期不够、长期逻辑未证实”
- 短线专家：
  - clarification 更强调“节奏 / 买点 / 风险控制 / 题材强弱”
  - self critique 更强调“量能不够、承接不足、龙头不明、情绪退潮”

---

## 6. 前端交互

### 6.1 发送流程

前端 `sendMessage()` 改为：

1. 用户发送消息
2. 若 `deepThink=false` 或 expert 不支持 clarification，直接走原 chat
3. 否则先调用 `/clarify/{expert_type}`
4. 在消息区插入一张 clarification 卡片
5. 用户点击某个选项或 `跳过，直接分析`
6. store 再发起正式 `chat`

### 6.2 卡片形态

clarification 卡片展示：

- 一句“我理解你的问题是……”
- `A/B/C/D` 四个按钮
- `跳过，直接分析` 按钮

按钮点击后：

- 卡片进入已选择状态
- 输入栏暂时禁用重复发送
- 正式 expert 流式回复开始

### 6.3 ThinkingPanel 展示

新增 thinking item：

- `clarification_request`
- `reasoning_summary`
- `self_critique`

其中：

- clarification 显示用户问题理解摘要和已选方向
- reasoning_summary 显示一段简短拆题摘要
- self_critique 显示风险、反方观点、缺失数据

---

## 7. 存储与兼容

不新增数据库表。

继续复用 `expert.messages.thinking JSON`，把新的 thinking item 存进去。

兼容要求：

- 历史消息没有这些 item 时，前端照常渲染
- 非 deepThink 请求不产生 clarification item
- 定时任务不触发 clarification，不受影响

---

## 8. 修改文件

后端：

- `backend/engine/expert/schemas.py`
- `backend/engine/expert/agent.py`
- `backend/engine/expert/routes.py`

前端：

- `frontend/types/expert.ts`
- `frontend/stores/useExpertStore.ts`
- `frontend/components/expert/ChatArea.tsx`
- `frontend/components/expert/MessageBubble.tsx`
- `frontend/components/expert/ThinkingPanel.tsx`
- `frontend/components/expert/InputBar.tsx`

测试：

- `tests/unit/expert/test_agent.py`
- `tests/unit/expert/test_routes.py`

---

## 9. 完成定义

本模块完成的标准：

1. `deepThink + rag/short_term` 首次发送时先出现 clarification 卡片
2. 选项中包含 `A/B/C/D` 风格入口和 `跳过，直接分析`
3. 用户选择后，expert 才进入正式分析
4. SSE 中能看到 `reasoning_summary` 与 `self_critique`
5. ThinkingPanel 能稳定展示上述结构
6. 定时任务与非 deepThink 对话不回归

---

## 10. 结论

这轮不是把 expert 变成“更啰嗦的流式回复”，而是把它升级成一个更像协作型分析伙伴的问答流程：

- 先确认问题
- 再明确分析方向
- 再深度拆题
- 最后自己质疑自己

实现上采取“`clarify` 独立 API + `chat` 扩展 SSE 事件”的方案，复杂度可控，也能最大化复用现有 expert 链路。
