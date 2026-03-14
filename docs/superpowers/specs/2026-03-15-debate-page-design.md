# 专家辩论页面设计 Spec

> 日期: 2026-03-15
> 状态: 待实现

## 目标

为 StockTerrain 新增专家辩论前端页面，将后端已有的 SSE 辩论系统（`POST /api/v1/debate`）可视化呈现，风格简约清新，多头 vs 空头采用逆转裁判式左右对立布局，裁判裁决有揭幕动画效果。

---

## 1. 导航架构

### 新增 `NavSidebar` 组件（两个页面共用）

- 路径: `web/components/ui/NavSidebar.tsx`
- 默认收起宽度: **48px**（仅图标）
- hover 展开宽度: **180px**（图标 + 文字标签）
- 展开/收起使用 CSS `transition: width 200ms ease-out`
- 两个导航入口:
  - 地形图 — `Mountain` 图标，跳转 `/`
  - 专家辩论 — `Scale` 图标，跳转 `/debate`
- 当前页高亮（accent 色背景圆角块）
- 使用 `next/navigation` 的 `usePathname` 判断当前路由

### NavSidebar 定位方式

`NavSidebar` 使用 `position: fixed`，固定在页面左边缘，`z-index: 50`，高度 `100vh`。不影响现有地形页的 fixed 覆盖层布局。地形页和辩论页的内容区均需在左侧预留 `48px` 空间（收起态），通过给 `<main>` 加 `ml-12` 实现。

### 改动现有页面

- `web/app/page.tsx`: 在 `<main>` 外层包一个 `<div className="flex">` 或直接在 body 层插入 `<NavSidebar />`（fixed 定位，不影响现有布局），内容区 `<main>` 加 `ml-12`
- 新建 `web/app/debate/page.tsx`

---

## 2. 辩论页布局（`/debate`）

### 整体结构

```
┌──┬──────────────────────────────────────────────────────┐
│  │                                                      │
│N │   多头区          发言流（中间）          空头区        │
│A │   🐂              scrollable               🐻        │
│V │   角色卡片         气泡列表               角色卡片      │
│  │                                                      │
│  ├──────────────────────────────────────────────────────┤
│  │  观察员栏: [散户情绪条] [主力动向]                     │
│  ├──────────────────────────────────────────────────────┤
│  │  🕐  [  输入股票代码，如 600519  ]  [轮数▾]  [开始辩论] │
└──┴──────────────────────────────────────────────────────┘
```

### 2.1 多头区 / 空头区（左右固定面板）

各占约 `w-56`，垂直居中对齐：

- 角色头像（大圆形，多头红色 `#EF4444` / 空头绿色 `#10B981` 渐变背景）
- 角色名称（`bull_expert` / `bear_expert`）
- 当前 stance 标签: `insist` / `partial_concede` / `concede`（颜色区分）
- 置信度进度条（`confidence` 字段，0~1）
- 认输时显示白旗 + 灰色遮罩

### 2.2 中间发言流（`TranscriptFeed`）

**路由规则：** `debate_entry` 事件按 `role` 字段分流：
- `role === 'bull_expert'` → 追加到发言流，气泡靠左
- `role === 'bear_expert'` → 追加到发言流，气泡靠右
- `role === 'retail_investor'` 或 `role === 'smart_money'` → **不**追加到发言流，转发给 `ObserverBar` 更新对应观察员状态

发言流具体：
- 可滚动区域，新消息自动滚动到底部
- 多头气泡: 靠左，红色左边框，浅红背景
- 空头气泡: 靠右，绿色右边框，浅绿背景
- 每条气泡包含:
  - 轮次标签 `Round N`
  - 发言内容 `argument`
  - 质疑列表 `challenges`（折叠展开，默认收起）
- 轮次分隔线: `--- Round N ---`（由 `debate_round_start` 事件触发）
- `data_fetching` 事件: 在发言流中插入一条 loading 提示条（"正在获取补充数据..."），`data_ready` 后移除
- `debate_end` 事件: 在发言流末尾插入系统消息，显示终止原因（如"多头认输 · 共 2 轮"）

### 2.3 观察员栏（底部固定条）

高度约 `h-16`，水平排列两个观察员卡片。由 `useDebateStore` 中的 `observerState` 驱动，每次收到对应角色的 `debate_entry` 事件时更新。

**散户投资者 (`retail_investor`)**:
- 情绪分进度条（`retail_sentiment_score` -1 ~ +1）
  - 正值（极度乐观/看多）→ 红色 `#EF4444`（A股红涨惯例）
  - 负值（极度悲观/看空）→ 绿色 `#10B981`
- 本轮是否发言：后端仅在 `speak: true` 时才推送 SSE 事件，`speak: false` 的观察员不会发出任何事件。因此"本轮沉默"状态由前端推断：若当前轮次结束（收到下一轮 `debate_round_start` 或 `debate_end`）时该观察员未收到任何发言事件，则显示"本轮沉默"。
- 发言内容折叠显示（默认收起，点击展开）

**主力资金 (`smart_money`)**:
- 无情绪分，只显示本轮是否发言 + 发言摘要（折叠）

### 2.4 底部输入栏

固定在页面底部，高度 `h-14`，三段式布局：

```
[🕐历史]  [股票代码输入框 flex-1]  [轮数下拉 1-5]  [开始辩论按钮]
```

- 历史按钮: `Clock` 图标，点击弹出历史弹窗
- 输入框: placeholder `"输入股票代码，如 600519"`，仅接受股票代码字符串，对应后端 `code` 字段
- 轮数下拉: 默认 3，范围 1-5，对应后端 `max_rounds` 字段
- 开始按钮: 点击后禁用整个输入栏，直到辩论结束（`status === 'completed'`）
- 辩论进行中显示 loading spinner + "辩论进行中..."
- 回放模式下整个输入栏隐藏

---

## 3. 历史辩论弹窗

- 触发: 点击底部 `Clock` 图标
- 样式: 居中 Modal，`max-w-md`，最大高度 `60vh` 可滚动
- 数据来源: `GET /api/v1/debate/history?limit=20`（需新增后端接口）

### 后端接口定义

`GET /api/v1/debate/history?limit=20`

查询 `shared.debate_records` 表。注意：`signal` 和 `debate_quality` 存储在 `judge_verdict_json` 字段的 JSON blob 中，不是独立列。后端实现需使用 DuckDB JSON 函数提取：

```sql
SELECT
  id AS debate_id,
  target,
  rounds_completed,
  termination_reason,
  created_at,
  json_extract_string(judge_verdict_json, '$.signal') AS signal,
  json_extract_string(judge_verdict_json, '$.debate_quality') AS debate_quality
FROM shared.debate_records
ORDER BY created_at DESC
LIMIT ?
```

返回：

```json
[
  {
    "debate_id": "600519_20260315143022",
    "target": "600519",
    "signal": "bullish",
    "debate_quality": "strong_disagreement",
    "rounds_completed": 3,
    "termination_reason": "max_rounds",
    "created_at": "2026-03-15T14:30:22+08:00"
  }
]
```

- 每条记录显示:
  - 标的代码
  - 时间（相对时间，如"3小时前"）
  - 裁判信号色点（红/绿/灰）+ 信号文字
  - 辩论质量标签（`consensus` / `strong_disagreement` / `one_sided`）
- 点击条目: 弹窗关闭，调用 `GET /api/v1/debate/{debate_id}` 加载完整记录，进入只读回放模式

### 回放模式后端接口

`GET /api/v1/debate/{debate_id}`

查询 `shared.debate_records` 表，使用主键列 `id`（不是 `debate_id`）：

```sql
SELECT * FROM shared.debate_records WHERE id = ?
```

返回：

```json
{
  "debate_id": "600519_20260315143022",
  "target": "600519",
  "blackboard_json": "...",
  "judge_verdict_json": "...",
  "rounds_completed": 3,
  "termination_reason": "max_rounds",
  "created_at": "2026-03-15T14:30:22+08:00"
}
```

前端解析 `blackboard_json.transcript` 重建发言流（仅使用 `role`/`round`/`argument`/`challenges`/`confidence`/`retail_sentiment_score` 字段；`data_requests[].result` 字段类型不定，前端忽略，不渲染）。解析 `judge_verdict_json` 直接展示裁判结论（跳过揭幕动画，直接显示静态结果卡片）。

---

## 4. 裁判裁决揭幕动画

触发条件: 收到 `judge_verdict` SSE 事件（实时辩论模式）

动画序列（使用 framer-motion）:

1. **遮罩淡入** (300ms): 全屏半透明黑色背景 `rgba(0,0,0,0.7)`
2. **卡片出现** (400ms): 中央白色卡片 `scale(0.8→1) + opacity(0→1)`，`ease-out`
3. **颜色轮盘** (1500ms): 顶部色块循环切换 红→绿→灰→红→绿→灰，先快后慢，最终定格在结论颜色。点击可跳过直接定格。
4. **内容淡入** (各 200ms 间隔依次出现):
   - 多头核心论点 vs 空头核心论点（左右对比）
   - 散户情绪注 + 主力动向注
   - 风险警示列表
   - 底部大字总结段落（`text-lg font-medium`）
5. **关闭按钮**: 右上角 `X`，关闭后回到辩论记录视图（可继续查看发言流）

颜色映射:
- `bullish` → `#EF4444`（红，看多）
- `bearish` → `#10B981`（绿，看空）
- `neutral` / `null` → `#9CA3AF`（灰）

回放模式下不播放揭幕动画，直接渲染静态结果卡片（无遮罩，嵌入页面底部）。

---

## 5. 数据流

### SSE 连接方式

后端 `POST /api/v1/debate` 使用 POST 方法，**不能使用浏览器原生 `EventSource`（仅支持 GET）**。

必须使用 `fetch` + `ReadableStream` 手动解析 SSE，且**必须直连后端**（`http://localhost:8000`），不能通过 Next.js rewrite proxy（proxy 会缓冲响应，破坏实时流）。使用 `NEXT_PUBLIC_API_BASE` 环境变量（与 `useTerrainStore` 相同模式）：

```ts
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000'

const res = await fetch(`${API_BASE}/api/v1/debate`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ code, max_rounds: maxRounds }),
})
const reader = res.body!.getReader()
// 逐行解析 "event: xxx\ndata: {...}\n\n" 格式
```

请求体: `{ code: string, max_rounds: number }`

### SSE 事件处理

| 事件 | 处理 |
|------|------|
| `debate_start` | 初始化 transcript/observerState，显示参与者 |
| `debate_round_start` | 在发言流插入轮次分隔线 |
| `debate_entry` (bull/bear) | 追加气泡到发言流，更新角色卡片 stance/confidence |
| `debate_entry` (observer) | 更新 ObserverBar 对应观察员状态，不进发言流 |
| `data_fetching` | 发言流插入 loading 提示条 |
| `data_ready` | 移除 loading 提示条 |
| `debate_end` | 发言流末尾插入系统消息（终止原因） |
| `judge_verdict` | 触发揭幕动画，更新 store.judgeVerdict |
| `error` | 显示错误 toast，重置 status 为 'idle' |

### 状态管理

新建 `web/stores/useDebateStore.ts`（zustand）:

```ts
interface ObserverState {
  speak: boolean
  argument: string
  retail_sentiment_score?: number  // 仅 retail_investor
}

interface DebateStore {
  status: 'idle' | 'debating' | 'final_round' | 'judging' | 'completed'
  transcript: DebateEntry[]          // 仅 bull/bear 发言
  observerState: Record<string, ObserverState>  // retail_investor / smart_money
  roleState: Record<string, { stance: string; confidence: number }>  // bull/bear 当前状态
  currentRound: number               // 当前轮次，用于推断观察员沉默
  judgeVerdict: JudgeVerdict | null
  isReplayMode: boolean
  error: string | null
  startDebate: (code: string, maxRounds: number) => void
  loadReplay: (debateId: string) => void
  reset: () => void
}

// status 与后端 Blackboard.status 对应:
// 'debating' → 普通轮次
// 'final_round' → 最终轮（UI 显示"最终轮"标识，由 debate_round_start.is_final 触发）
// 'judging' → 等待裁判（debate_end 后）
// 'completed' → 结束（judge_verdict 后）
```

---

## 6. 文件结构

```
web/
  app/
    debate/
      page.tsx              # 辩论页主入口
  components/
    ui/
      NavSidebar.tsx        # 共用左侧导航（新增，fixed 定位）
    debate/
      DebatePage.tsx        # 辩论页根组件
      BullBearArena.tsx     # 左中右三栏布局
      RoleCard.tsx          # 角色卡片（多头/空头）
      TranscriptFeed.tsx    # 中间发言流（含路由逻辑）
      SpeechBubble.tsx      # 单条发言气泡
      ObserverBar.tsx       # 底部观察员栏
      InputBar.tsx          # 底部输入栏
      HistoryModal.tsx      # 历史辩论弹窗
      JudgeVerdictOverlay.tsx # 裁判揭幕动画（实时）/ 静态结果卡片（回放）
  stores/
    useDebateStore.ts       # 辩论状态管理（新增）
  types/
    debate.ts               # 前端类型定义（新增）

engine/
  api/routes/debate.py      # 新增 GET /debate/history + GET /debate/{debate_id}
```

---

## 7. 设计约束

- 复用现有 CSS 变量（`--accent`, `--bg-primary`, `--border` 等）
- 动画库: framer-motion（已安装）
- 图标库: lucide-react（已安装）
- 不引入新依赖
- 辩论进行中不允许重复发起新辩论
- LLM 未配置时（后端返回 503）底部显示友好提示，禁用开始按钮
- `NavSidebar` 使用 `position: fixed`，不破坏现有地形页布局
