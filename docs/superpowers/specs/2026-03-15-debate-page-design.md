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

### 改动现有页面

- `web/app/page.tsx`: 在 `<main>` 内左侧插入 `<NavSidebar />`，内容区加 `pl-12`（收起态留白）
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
│  │  🕐  [  输入议题或股票代码...  ]  [轮数▾]  [开始辩论]  │
└──┴──────────────────────────────────────────────────────┘
```

### 2.1 多头区 / 空头区（左右固定面板）

各占约 `w-56`，垂直居中对齐：

- 角色头像（大圆形，多头红色 `#EF4444` / 空头绿色 `#10B981` 渐变背景）
- 角色名称（`bull_expert` / `bear_expert`）
- 当前 stance 标签: `insist` / `partial_concede` / `concede`（颜色区分）
- 置信度进度条（`confidence` 字段，0~1）
- 认输时显示白旗 + 灰色遮罩

### 2.2 中间发言流

- 可滚动区域，新消息自动滚动到底部
- 多头气泡: 靠左，红色左边框，浅红背景
- 空头气泡: 靠右，绿色右边框，浅绿背景
- 每条气泡包含:
  - 轮次标签 `Round N`
  - 发言内容 `argument`
  - 质疑列表 `challenges`（折叠展开）
  - 数据请求 loading 提示（`data_fetching` 事件）
- 轮次分隔线: `--- Round N ---`

### 2.3 观察员栏（底部固定条）

高度约 `h-16`，水平排列两个观察员卡片：

**散户投资者 (`retail_investor`)**:
- 情绪分进度条（`retail_sentiment_score` -1 ~ +1，负值绿色/正值红色）
- 本轮是否发言（`speak: false` 时显示"本轮沉默"）
- 发言内容折叠显示

**主力资金 (`smart_money`)**:
- 同上，无情绪分，只显示发言摘要

### 2.4 底部输入栏

固定在页面底部，高度 `h-14`，三段式布局：

```
[🕐历史]  [议题输入框 flex-1]  [轮数下拉 1-5]  [开始辩论按钮]
```

- 历史按钮: `Clock` 图标，点击弹出历史弹窗
- 输入框: placeholder `"输入股票代码或议题，如 600519 或 '白酒板块前景'"`
- 轮数下拉: 默认 3，范围 1-5
- 开始按钮: 点击后禁用整个输入栏，直到辩论结束
- 辩论进行中显示 loading spinner + "辩论进行中..."

---

## 3. 历史辩论弹窗

- 触发: 点击底部 `Clock` 图标
- 样式: 居中 Modal，`max-w-md`，最大高度 `60vh` 可滚动
- 数据来源: `GET /api/v1/debate/history`（需新增后端接口，返回 `shared.debate_records` 列表）
- 每条记录显示:
  - 标的代码
  - 时间（相对时间，如"3小时前"）
  - 裁判信号色点（红/绿/灰）+ 信号文字
  - 辩论质量标签（`consensus` / `strong_disagreement` / `one_sided`）
- 点击条目: 弹窗关闭，右侧加载该次辩论记录（只读回放模式，输入栏隐藏）

---

## 4. 裁判裁决揭幕动画

触发条件: 收到 `judge_verdict` SSE 事件

动画序列（使用 framer-motion）:

1. **遮罩淡入** (300ms): 全屏半透明黑色背景 `rgba(0,0,0,0.7)`
2. **卡片出现** (400ms): 中央白色卡片 `scale(0.8→1) + opacity(0→1)`，`ease-out`
3. **颜色轮盘** (1500ms): 顶部色块循环切换 红→绿→灰→红→绿→灰，先快后慢，最终定格在结论颜色
4. **内容淡入** (各 200ms 间隔依次出现):
   - 多头核心论点 vs 空头核心论点（左右对比）
   - 散户情绪注 + 主力动向注
   - 风险警示列表
   - 底部大字总结段落（`text-lg font-medium`）
5. **关闭按钮**: 右上角 `X`，关闭后回到辩论记录视图

颜色映射:
- `bullish` → `#EF4444`（红）
- `bearish` → `#10B981`（绿）
- `neutral` → `#9CA3AF`（灰）

---

## 5. 数据流

### SSE 事件处理

前端通过 `EventSource` 或 `fetch` + `ReadableStream` 消费 `POST /api/v1/debate` 的 SSE 流：

| 事件 | 处理 |
|------|------|
| `debate_start` | 初始化 Blackboard 状态，显示参与者 |
| `debate_round_start` | 添加轮次分隔线 |
| `debate_entry` | 追加气泡，更新角色卡片（stance/confidence） |
| `data_fetching` | 中间显示 loading 条 |
| `data_ready` | 移除 loading 条 |
| `debate_end` | 显示终止原因 |
| `judge_verdict` | 触发揭幕动画 |
| `error` | 显示错误提示 |

### 新增后端接口

`GET /api/v1/debate/history?limit=20` — 返回最近 N 条辩论记录摘要

### 状态管理

新建 `web/stores/useDebateStore.ts`（zustand）:

```ts
interface DebateStore {
  status: 'idle' | 'debating' | 'judging' | 'completed'
  blackboard: Blackboard | null
  transcript: DebateEntry[]
  judgeVerdict: JudgeVerdict | null
  isReplayMode: boolean
  startDebate: (topic: string, maxRounds: number) => void
  loadReplay: (debateId: string) => void
  reset: () => void
}
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
      NavSidebar.tsx        # 共用左侧导航（新增）
    debate/
      DebatePage.tsx        # 辩论页根组件
      BullBearArena.tsx     # 左中右三栏布局
      RoleCard.tsx          # 角色卡片（多头/空头）
      TranscriptFeed.tsx    # 中间发言流
      SpeechBubble.tsx      # 单条发言气泡
      ObserverBar.tsx       # 底部观察员栏
      InputBar.tsx          # 底部输入栏
      HistoryModal.tsx      # 历史辩论弹窗
      JudgeVerdictOverlay.tsx # 裁判揭幕动画
  stores/
    useDebateStore.ts       # 辩论状态管理（新增）
  types/
    debate.ts               # 前端类型定义（新增）

engine/
  api/routes/debate.py      # 新增 GET /api/v1/debate/history
```

---

## 7. 设计约束

- 复用现有 CSS 变量（`--accent`, `--bg-primary`, `--border` 等）
- 动画库: framer-motion（已安装）
- 图标库: lucide-react（已安装）
- 不引入新依赖
- 辩论进行中不允许重复发起新辩论
- LLM 未配置时底部显示友好提示，禁用开始按钮
