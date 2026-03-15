# 终止辩论 + 可选总结 设计文档

## 背景

当前辩论一旦开始无法中途终止，用户只能等待辩论自然结束。需要提供终止能力，并在终止后询问用户是否需要 AI 对已有内容进行总结。

## 方案：前端 AbortController + 后端 summarize 端点

---

## 类型变更

**`web/types/debate.ts`**
- `DebateStatus` 新增 `"stopped"` 状态：
  ```ts
  export type DebateStatus = "idle" | "debating" | "final_round" | "judging" | "completed" | "stopped";
  ```
- 新增 `PartialSummary` 类型（summarize 端点响应）：
  ```ts
  export interface PartialSummary {
    summary: string;
    signal: DebateSignal | null;
  }
  ```

---

## 前端改动

### useDebateStore

新增字段：
- `_abortController: AbortController | null` — 持有当前 SSE 连接的 abort 控制器
- `currentTarget: string | null` — 当前辩论的股票代码，`startDebate` 时存入，`reset()` 时清为 null

新增方法：
- `stopDebate()` — 调用 `_abortController?.abort()`，设置 `status: "stopped"`

`startDebate` 改动：
1. 调用 `reset()` 后（reset 会清理旧 controller 和 currentTarget），立即 `set({ currentTarget: code })`
2. 创建新 `AbortController`，立即 `set({ _abortController: controller })`（在 fetch 调用之前，确保 `stopDebate()` 能引用到它）
3. `fetch` 传入 `signal: controller.signal`
3. catch 块中检查 `e instanceof DOMException && e.name === "AbortError"`，若是则跳过 `set({ error, status })`，因为 `stopDebate()` 已设置正确状态

`_handleSSEEvent` 改动：
- 函数入口处检查 `get().status === "stopped"`，若是则直接 return，防止 abort 传播窗口内的 set 覆盖 stopped 状态

`reset()` 改动：
- 清理 `_abortController: null`

### InputBar

props 变更：新增 `onStop: () => void`（与现有 `onStart` 保持一致，不直接访问 store）

行为：
- `status` 为 `"debating" | "final_round" | "judging"` 时，将"辩论中..."按钮替换为红色"终止"按钮
- 点击终止按钮后立即 disabled，防止重复点击（abort 传播期间）

### StopConfirmModal（新组件）

**可见性控制**：由 `DebatePage` 根据 `status === "stopped"` 派生，不在 store 里存 UI 状态

**弹窗内容**：
- 标题："辩论已终止"
- 两个按钮："生成总结" / "直接退出"

**"生成总结"流程**：
1. 过滤 `transcript`：`transcript.filter(i => i.type === "entry").map(i => i.data)` 得到 `DebateEntry[]`
2. 调用 `POST /api/v1/debate/summarize`，传入 `{ transcript: DebateEntry[], target: string }`
3. 加载中：按钮显示 spinner，禁用交互
4. 成功：关闭弹窗，在 TranscriptFeed 末尾展示 `SummaryCard`（新组件，只需 `summary` + `signal`，不复用完整 VerdictCard）
5. 失败：弹窗内显示错误提示，保留两个按钮供用户重试或直接退出

**"直接退出"**：调用 `store.reset()`

**关闭弹窗（Escape / 点击遮罩）**：等同于"直接退出"，调用 `store.reset()`

### DebatePage

- 从 store 取 `stopDebate`，传给 `InputBar` 的 `onStop`
- 根据 `status === "stopped"` 渲染 `<StopConfirmModal>`
- `StopConfirmModal` 需要 `transcript`、`target`（从 `store.currentTarget` 取，不用 `judgeVerdict?.target`，因为终止时 judgeVerdict 始终为 null）

### SummaryCard（新组件，TranscriptFeed 内）

只展示 `summary` 文本和 `signal` 颜色标签，不需要完整 JudgeVerdict 字段。

---

## 后端改动

**新增端点 `POST /api/v1/debate/summarize`**

```
Request:  { transcript: list[DebateEntry], target: str }
Response: { summary: str, signal: "bullish" | "bearish" | "neutral" | null }
```

- 接收前端已过滤的 `DebateEntry` 列表
- 调用 LLM，prompt 要求：基于已有辩论内容，给出简短总结和倾向判断
- 独立端点，不依赖完整辩论流程，可复用

---

## 数据流

```
用户点击"终止"
  → InputBar.onStop() → store.stopDebate()
    → abortController.abort()
    → set({ status: "stopped" })
  → fetch catch 检测 AbortError → 跳过 error set
  → _handleSSEEvent 检测 status==="stopped" → 跳过后续 set
  → DebatePage 检测 status==="stopped" → 渲染 StopConfirmModal

用户选"生成总结"
  → 过滤 transcript → POST /api/v1/debate/summarize
  → 成功 → 关闭弹窗，TranscriptFeed 末尾显示 SummaryCard
  → 失败 → 弹窗内显示错误，可重试

用户选"直接退出" / Escape
  → store.reset() → status: "idle"，弹窗消失
```

---

## 文件改动清单

| 文件 | 改动类型 |
|------|---------|
| `web/types/debate.ts` | 新增 `"stopped"` 到 DebateStatus，新增 `PartialSummary` 类型 |
| `web/stores/useDebateStore.ts` | 新增 `_abortController`、`stopDebate()`，修改 `startDebate` catch 和 `_handleSSEEvent` |
| `web/components/debate/InputBar.tsx` | 新增 `onStop` prop，辩论中显示终止按钮 |
| `web/components/debate/StopConfirmModal.tsx` | 新建弹窗组件 |
| `web/components/debate/SummaryCard.tsx` | 新建简版总结卡片组件 |
| `web/components/debate/DebatePage.tsx` | 传 `onStop`，挂载 StopConfirmModal，传 target |
| `engine/api/routes/debate.py` | 新增 `POST /debate/summarize` 端点 |

---

## 不在范围内

- 后端 task 取消机制（方案 B）
- 多用户并发辩论管理
- 终止后自动保存到历史记录
