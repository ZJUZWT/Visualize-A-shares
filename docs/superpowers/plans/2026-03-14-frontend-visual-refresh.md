# StockTerrain 前端视觉美化 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 纯视觉层美化 StockTerrain 前端 — 毛玻璃精炼、Emoji→Lucide 图标、单侧栏+底部浮动工具栏布局、细节打磨。

**Architecture:** 改动 6 个文件（globals.css、page.tsx、Sidebar.tsx、TopBar.tsx、AIChatPanel.tsx、RelatedStocksPanel.tsx），加 terrain.ts 一个标签值。不动数据接口、TypeScript 类型定义、Three.js 渲染逻辑。不新增 npm 依赖。

**Tech Stack:** Next.js 15 / React 19 / Tailwind CSS v4 / lucide-react / framer-motion

**Spec:** `docs/superpowers/specs/2026-03-14-frontend-visual-refresh-design.md`

**约束（红线）:**
- `terrain.ts` 的 `Z_METRIC_ICONS` 类型签名不动（保持 `Record<ZMetric, string>`）
- `StockNodes.tsx`、`TerrainMesh.tsx` 不动
- `useTerrainStore.ts`、`useChatStore.ts` 不动
- 不新增 npm 依赖

---

## File Map

| 文件 | 操作 | 职责 |
|------|------|------|
| `web/app/globals.css` | Modify | 配色变量、glass-panel、阴影、过渡曲线、按钮圆角、canvas 背景 |
| `web/app/page.tsx` | Modify | bg-transparent、版本号 v3.1 |
| `web/types/terrain.ts` | Modify | 仅 `rise_prob` 标签移除 emoji 前缀（1 行） |
| `web/components/ui/Sidebar.tsx` | Modify | 图标替换、布局重组（LeftPanel 精简 + BottomToolbar 新增）、面板头样式 |
| `web/components/ui/TopBar.tsx` | Modify | lucide 图标、⌘K 装饰、定位调整 right-4 |
| `web/components/ui/AIChatPanel.tsx` | Modify | lucide 图标替换、AnimatePresence 退出动画 |
| `web/components/ui/RelatedStocksPanel.tsx` | Modify | lucide 图标替换 |

---

## Chunk 1: CSS 基础层 + page.tsx

### Task 1: globals.css — 配色变量与阴影系统

**Files:**
- Modify: `web/app/globals.css:3-23` (`:root` 变量块)

- [ ] **Step 1: 更新 `:root` CSS 变量**

在 `web/app/globals.css` 中修改 `:root` 块：

```css
:root {
  --bg-primary: #F8FAFE;
  --bg-secondary: #FFFFFF;
  --bg-card: #FFFFFF;
  --border: #E8ECF4;
  --border-hover: #D0D8E8;
  --text-primary: #0F172A;    /* 改：从 #1A1D26 加深 */
  --text-secondary: #6B7280;
  --text-tertiary: #9CA3AF;
  --accent: #4F8EF7;
  --accent-light: #EBF2FF;
  --accent-hover: #3B7DE6;
  --red-stock: #EF4444;
  --red-light: #FEF2F2;
  --green-stock: #10B981;     /* 改：从 #22C55E 改为 emerald */
  --green-light: #ECFDF5;     /* 改：配合新绿色 */
  --shadow-xs: 0 1px 2px rgba(0, 0, 0, 0.03);                  /* 新增 */
  --shadow-sm: 0 2px 4px -1px rgba(0, 0, 0, 0.04);             /* 改：加 negative spread */
  --shadow-md: 0 4px 12px -2px rgba(0, 0, 0, 0.06);            /* 改：加 negative spread */
  --shadow-lg: 0 8px 24px -4px rgba(0, 0, 0, 0.08);            /* 改：加 negative spread */
  --shadow-xl: 0 16px 48px -8px rgba(0, 0, 0, 0.10);           /* 新增 */
  --radius: 12px;             /* 改：从 14px 微调 */
  --ease-out-expo: cubic-bezier(0.16, 1, 0.3, 1);              /* 新增 */
}
```

- [ ] **Step 2: Commit**

```bash
git add web/app/globals.css
git commit -m "style: 更新 CSS 变量 — 配色、阴影系统、圆角、过渡曲线"
```

### Task 2: globals.css — glass-panel 精炼

**Files:**
- Modify: `web/app/globals.css:83-96` (`.glass-panel` 和 `.glass-panel:hover`)

- [ ] **Step 1: 替换 glass-panel 样式**

将 `.glass-panel` 和 `.glass-panel:hover` 替换为：

```css
.glass-panel {
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(24px) saturate(1.5);
  -webkit-backdrop-filter: blur(24px) saturate(1.5);
  border: 1px solid rgba(255, 255, 255, 0.6);
  border-top: 1px solid rgba(255, 255, 255, 0.8);
  border-radius: var(--radius);
  box-shadow:
    0 4px 12px rgba(0, 0, 0, 0.04),
    inset 0 1px 0 rgba(255, 255, 255, 0.5);
}

.glass-panel:hover {
  background: rgba(255, 255, 255, 0.88);
  border-color: rgba(255, 255, 255, 0.7);
  box-shadow:
    0 8px 24px rgba(0, 0, 0, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.6);
}
```

- [ ] **Step 2: Commit**

```bash
git add web/app/globals.css
git commit -m "style: 精炼 glass-panel — 内发光、border-top 高光、柔和阴影"
```

### Task 3: globals.css — canvas 背景渐变 + 过渡曲线 + 按钮圆角

**Files:**
- Modify: `web/app/globals.css:63-71` (`.canvas-container`)
- Modify: `web/app/globals.css:218-221` (`.transition-smooth`)
- Modify: `web/app/globals.css:112-127` (`.btn-primary`, `.btn-secondary`)

- [ ] **Step 1: 更新 canvas-container 背景**

给 `.canvas-container` 添加渐变背景：

```css
.canvas-container {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  z-index: 0;
  background: radial-gradient(
    ellipse at 30% 20%,
    #EEF4FF 0%,
    #F8FAFE 40%,
    #FDF8F5 70%,
    #F5F7FA 100%
  );
}
```

- [ ] **Step 2: 更新 transition-smooth 曲线**

```css
.transition-smooth {
  transition: all 0.25s var(--ease-out-expo);
}
```

- [ ] **Step 3: 按钮圆角 10px → 8px**

`.btn-primary` 和 `.btn-secondary` 的 `border-radius: 10px` 改为 `border-radius: 8px`。

- [ ] **Step 4: Commit**

```bash
git add web/app/globals.css
git commit -m "style: canvas 渐变背景、expo 过渡曲线、按钮圆角统一 8px"
```

### Task 4: page.tsx — 背景透明 + 版本号

**Files:**
- Modify: `web/app/page.tsx:37` (`bg-[#EEF2F7]` → `bg-transparent`)
- Modify: `web/app/page.tsx:50` (版本号)

- [ ] **Step 1: 修改 page.tsx**

1. 第 37 行 `<main>` 的 `bg-[#EEF2F7]` 改为 `bg-transparent`
2. 第 50 行 `StockTerrain v2.0` 改为 `StockTerrain v3.1`

- [ ] **Step 2: Commit**

```bash
git add web/app/page.tsx
git commit -m "style: page.tsx 背景透明化、版本号更新 v3.1"
```

### Task 5: terrain.ts — 移除 rise_prob 标签 emoji

**Files:**
- Modify: `web/types/terrain.ts:128` (仅 1 行)

- [ ] **Step 1: 修改标签值**

第 128 行 `rise_prob: "🔮 明日上涨概率"` 改为 `rise_prob: "明日上涨概率"`

- [ ] **Step 2: Commit**

```bash
git add web/types/terrain.ts
git commit -m "style: 移除 rise_prob 标签的 emoji 前缀"
```

---

## Chunk 2: AIChatPanel + RelatedStocksPanel + TopBar 图标替换

### Task 6: AIChatPanel.tsx — Emoji → Lucide 图标 + AnimatePresence

**Files:**
- Modify: `web/components/ui/AIChatPanel.tsx`

- [ ] **Step 1: 添加 lucide-react 和 framer-motion imports**

在文件顶部 import 区域添加：

```tsx
import { MessageCircle, X, Key, Sparkles, Lightbulb, EyeOff, Eye } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
```

- [ ] **Step 2: 替换浮动按钮图标**

第 30 行区域，将 `🤖` 和 `✕` 替换：

```tsx
{isPanelOpen ? <X className="w-5 h-5" /> : <MessageCircle className="w-5 h-5" />}
```

- [ ] **Step 3: 替换面板标题图标**

第 86-87 行区域：
- `<span className="text-base">🤖</span>` → `<MessageCircle className="w-4 h-4 text-[var(--accent)]" />`

- [ ] **Step 4: 替换 EmptyState 图标**

EmptyState 组件中：
- 无 API Key 状态：`🔑` → `<Key className="w-8 h-8 text-[var(--accent)]" />`（外层 div 中的 emoji）
- 有 API Key 状态：`🤖` → `<Sparkles className="w-7 h-7 text-[var(--accent)]" />`
- 建议按钮前缀：`💡 {s}` → `<Lightbulb className="w-3 h-3 inline mr-1.5 text-[var(--text-tertiary)]" />{s}`

- [ ] **Step 5: 替换 ConfigPanel 图标**

- 显示/隐藏密码按钮：`{showKey ? "🙈" : "👁️"}` → `{showKey ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}`
- 保存按钮：`"✓ 保存配置"` → `"保存配置"`
- 提示信息：移除 `💡` 和 `📡` emoji 前缀

- [ ] **Step 6: 添加 AnimatePresence 到 ChatWindow**

重构方式：`ChatWindow` 函数保留，但移除它的外层 `<div>` 包装（当前第 82 行的 `overlay fixed...animate-in` div）。改由 AIChatPanel 中用 `motion.div` 提供外壳。

**AIChatPanel 的 render 改为：**

```tsx
<AnimatePresence>
  {isPanelOpen && (
    <motion.div
      key="chat-window"
      initial={{ opacity: 0, y: 12, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 8, scale: 0.98 }}
      transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
      className="overlay fixed bottom-20 right-6 w-[400px] h-[560px] flex flex-col glass-panel shadow-2xl z-40 overflow-hidden"
    >
      <ChatWindowContent />
    </motion.div>
  )}
</AnimatePresence>
```

**ChatWindow 函数改为 ChatWindowContent：** 将当前 `ChatWindow` 函数重命名为 `ChatWindowContent`，并将其 return 语句中的最外层 `<div className="overlay fixed bottom-20...animate-in">` 替换为 `<>...</>`（React Fragment），因为外壳已由 `motion.div` 提供。即：

```tsx
// 改前 (ChatWindow, line 82)
return (
  <div className="overlay fixed bottom-20 right-6 w-[400px] h-[560px] flex flex-col glass-panel shadow-2xl z-40 overflow-hidden animate-in">
    {/* 顶栏、消息列表、输入框 */}
  </div>
);

// 改后 (ChatWindowContent)
return (
  <>
    {/* 顶栏、消息列表、输入框 — 内容完全不变 */}
  </>
);
```

这样 `motion.div` 承担定位和动画职责，`ChatWindowContent` 只负责内容。

- [ ] **Step 7: 验证 AnimatePresence 正常工作**

Run: `cd web && npm run dev`

在浏览器中点击 AI 聊天浮动按钮，确认：
1. 面板弹出有 fade+slide 入场动画
2. 面板关闭有 fade+slide 退出动画
3. 无 SSR hydration 报错（检查浏览器控制台）

- [ ] **Step 8: Commit**

```bash
git add web/components/ui/AIChatPanel.tsx
git commit -m "style: AIChatPanel Emoji→Lucide 图标 + AnimatePresence 退出动画"
```

### Task 7: RelatedStocksPanel.tsx — Emoji → Lucide 图标

**Files:**
- Modify: `web/components/ui/RelatedStocksPanel.tsx`

- [ ] **Step 1: 添加 lucide import**

```tsx
import { Link as LinkIcon, Pin } from "lucide-react";
```

- [ ] **Step 2: 替换图标**

- 第 37 行标题 `🔗 关联股票` → `<LinkIcon className="w-3.5 h-3.5" /> 关联股票`（用 flex gap 排列）
- 第 47 行选中标记 `📌` → `<Pin className="w-3 h-3 text-[var(--accent)]" />`

- [ ] **Step 3: Commit**

```bash
git add web/components/ui/RelatedStocksPanel.tsx
git commit -m "style: RelatedStocksPanel Emoji→Lucide 图标"
```

### Task 8: TopBar.tsx — Lucide 图标 + ⌘K 装饰 + 定位调整

**Files:**
- Modify: `web/components/ui/TopBar.tsx`

- [ ] **Step 1: 添加 lucide import**

```tsx
import { Search, X } from "lucide-react";
```

- [ ] **Step 2: 替换搜索图标**

第 62-71 行的 SVG 搜索图标替换为：
```tsx
<Search className="w-4 h-4 text-[var(--text-tertiary)] mr-2 flex-shrink-0" />
```

- [ ] **Step 3: 替换关闭按钮图标**

第 91 行区域的 SVG 关闭图标替换为：
```tsx
<X className="w-3.5 h-3.5" />
```

- [ ] **Step 4: 添加 ⌘K 快捷键装饰**

在搜索输入框容器（`<div className="flex items-center px-4 py-2.5">`）内，关闭按钮之后、容器结束之前，添加：

```tsx
{!searchQuery && (
  <kbd className="ml-auto text-[10px] text-[var(--text-tertiary)] bg-gray-100 px-1.5 py-0.5 rounded font-mono border border-[var(--border)] flex-shrink-0">
    ⌘K
  </kbd>
)}
```

（仅在无搜索内容时显示，有内容时显示清除按钮）

- [ ] **Step 5: 调整定位 — 移除右侧面板留空**

第 58 行 `right-[260px]` 改为 `right-4`

- [ ] **Step 6: 添加 AnimatePresence 到搜索下拉**

将搜索结果下拉（第 99-128 行 `{searchResults.length > 0 && ...}`）包裹 AnimatePresence：

```tsx
import { AnimatePresence, motion } from "framer-motion";

<AnimatePresence>
  {searchResults.length > 0 && (
    <motion.div
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4 }}
      transition={{ duration: 0.15, ease: [0.16, 1, 0.3, 1] }}
      className="absolute top-full left-0 right-0 mt-1.5 glass-panel py-1 max-h-[300px] overflow-y-auto"
    >
      {/* 原有搜索结果列表内容不变 */}
    </motion.div>
  )}
</AnimatePresence>
```

- [ ] **Step 7: Commit**

```bash
git add web/components/ui/TopBar.tsx
git commit -m "style: TopBar Lucide 图标 + ⌘K 装饰 + right-4 定位 + 下拉动画"
```

---

## Chunk 3: Sidebar.tsx 全面改造（最大任务）

### Task 9: Sidebar.tsx — Lucide imports + METRIC_ICON_COMPONENTS + CollapsiblePanel icon 类型

**Files:**
- Modify: `web/components/ui/Sidebar.tsx:1-25` (imports 区)
- Modify: `web/components/ui/Sidebar.tsx:622-668` (CollapsiblePanel 组件)

- [ ] **Step 1: 添加 lucide 和 framer-motion imports**

在文件顶部添加：

```tsx
import {
  BarChart3, Mountain, FileText, Eye, Settings2, History,
  Activity, Palette, TrendingUp, RefreshCw, DollarSign,
  BookOpen, Scale, Sparkles, Tag, Grid3x3, Waves, Minimize2, GripVertical,
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
```

- [ ] **Step 2: 添加 METRIC_ICON_COMPONENTS 本地映射**

在 imports 之后、`Sidebar` 组件之前添加：

```tsx
const METRIC_ICON_COMPONENTS: Record<ZMetric, React.ComponentType<{ className?: string }>> = {
  pct_chg: TrendingUp,
  turnover_rate: RefreshCw,
  volume: BarChart3,
  amount: DollarSign,
  pe_ttm: FileText,
  pb: BookOpen,
  wb_ratio: Scale,
  rise_prob: Sparkles,
};
```

- [ ] **Step 3: 修改 CollapsiblePanel — icon prop 改为 ReactNode**

将 `icon?: string` 改为 `icon?: React.ReactNode`，渲染部分：

```tsx
// 改前
{icon && <span className="text-xs">{icon}</span>}
<span className="text-[11px] font-semibold text-[var(--text-tertiary)] uppercase tracking-wider">

// 改后
{icon && <span className="text-[var(--text-tertiary)]">{icon}</span>}
<span className="text-xs font-medium text-[var(--text-secondary)]">
```

去掉 `uppercase tracking-wider`。

- [ ] **Step 4: Commit**

```bash
git add web/components/ui/Sidebar.tsx
git commit -m "style: Sidebar lucide imports + METRIC_ICON_COMPONENTS + CollapsiblePanel 面板头轻量化"
```

### Task 10: Sidebar.tsx — LeftPanel 图标替换 + 布局精简

**Files:**
- Modify: `web/components/ui/Sidebar.tsx` (LeftPanel 函数)

- [ ] **Step 1: Logo 版本号**

第 72 行 `v3.0` 改为 `v3.1`

- [ ] **Step 2: 操作按钮 — 移除 emoji**

- 第 108 行 `"🔄 刷新地形数据"` → `"刷新地形数据"`
- 第 110 行 `"🏔️ 生成 3D 地形"` → `"生成 3D 地形"`
- 第 83 行 `📸 展示模式` → `展示模式 · 数据快照`
- 第 148 行 `❌ {error}` → `{error}`

- [ ] **Step 3: Z 轴指标 — CollapsiblePanel icon 改为 lucide**

第 160 行：`icon="📊"` → `icon={<BarChart3 className="w-3.5 h-3.5" />}`

- [ ] **Step 4: Z 轴指标 — 改为 2 列网格布局**

将第 161 行 `<div className="flex flex-col gap-1">` 改为 `<div className="grid grid-cols-2 gap-1">`

指标按钮中的 emoji 图标替换：

```tsx
// 改前
<span>{Z_METRIC_ICONS[key]}</span>

// 改后
{(() => {
  const IconComp = METRIC_ICON_COMPONENTS[key];
  return <IconComp className="w-3.5 h-3.5" />;
})()}
```

- [ ] **Step 5: 地形控制 — 精简为 2 个核心滑块**

第 185 行 CollapsiblePanel icon：`icon="🏔️"` → `icon={<Mountain className="w-3.5 h-3.5" />}`

保留「高度缩放」和「XY 整体缩放」两个 SliderControl。

移除以下 SliderControl（移到后续 Task 的 BottomToolbar 高级设置面板）：
- 核平滑半径（第 196-207 行）
- 网格分辨率（第 209-220 行）
- X 轴比例（第 251-263 行）
- Y 轴比例（第 264-274 行）
- "应用核半径/分辨率" 按钮（第 222-237 行）

保留的滑块在高度缩放之后直接接 XY 整体缩放（中间用 `<div className="mt-2.5">` 间隔）。

- [ ] **Step 6: 数据概览 — CollapsiblePanel icon**

第 279 行：`icon="📋"` → `icon={<FileText className="w-3.5 h-3.5" />}`

- [ ] **Step 7: 新增显示开关图标行**

在数据概览面板之后、`</div>` (LeftPanel 结束) 之前，添加显示开关区域。从 LeftPanel 内访问 store 需要添加对应的 state/action（`showLabels`, `showGrid`, `showContours`, `flattenBalls`, `showDropLines` 和 toggle 函数）到 LeftPanel 的 useTerrainStore 解构中。

```tsx
{/* ─── 显示开关（图标行）──────────────── */}
{terrainData && (
  <div className="glass-panel px-4 py-3">
    <div className="text-xs font-medium text-[var(--text-secondary)] mb-2">显示</div>
    <div className="flex gap-1.5">
      <button
        onClick={toggleLabels}
        title="股票标签"
        className={`w-8 h-8 rounded-lg flex items-center justify-center transition-smooth ${
          showLabels ? "bg-[var(--accent-light)] text-[var(--accent)]" : "bg-gray-50 text-[var(--text-tertiary)]"
        }`}
      >
        <Tag className="w-3.5 h-3.5" />
      </button>
      <button
        onClick={toggleGrid}
        title="底部网格"
        className={`w-8 h-8 rounded-lg flex items-center justify-center transition-smooth ${
          showGrid ? "bg-[var(--accent-light)] text-[var(--accent)]" : "bg-gray-50 text-[var(--text-tertiary)]"
        }`}
      >
        <Grid3x3 className="w-3.5 h-3.5" />
      </button>
      <button
        onClick={toggleContours}
        title="等高线"
        className={`w-8 h-8 rounded-lg flex items-center justify-center transition-smooth ${
          showContours ? "bg-[var(--accent-light)] text-[var(--accent)]" : "bg-gray-50 text-[var(--text-tertiary)]"
        }`}
      >
        <Waves className="w-3.5 h-3.5" />
      </button>
      <button
        onClick={toggleFlattenBalls}
        title="球体拍平"
        className={`w-8 h-8 rounded-lg flex items-center justify-center transition-smooth ${
          flattenBalls ? "bg-[var(--accent-light)] text-[var(--accent)]" : "bg-gray-50 text-[var(--text-tertiary)]"
        }`}
      >
        <Minimize2 className="w-3.5 h-3.5" />
      </button>
      <button
        onClick={toggleDropLines}
        title="价格垂线"
        className={`w-8 h-8 rounded-lg flex items-center justify-center transition-smooth ${
          showDropLines ? "bg-[var(--accent-light)] text-[var(--accent)]" : "bg-gray-50 text-[var(--text-tertiary)]"
        }`}
      >
        <GripVertical className="w-3.5 h-3.5" />
      </button>
    </div>
  </div>
)}
```

- [ ] **Step 7a: 更新 LeftPanel 的 useTerrainStore 解构**

**必须先做此步，否则编译失败。** 在 LeftPanel 函数的 `useTerrainStore()` 解构中（当前约第 30-53 行），添加以下字段：

```tsx
const {
  // ... 已有字段保留 ...
  showLabels,
  showGrid,
  showContours,
  flattenBalls,
  showDropLines,
  toggleLabels,
  toggleGrid,
  toggleContours,
  toggleFlattenBalls,
  toggleDropLines,
} = useTerrainStore();
```

这些字段当前仅在 RightPanel 中解构（第 306-332 行），需要复制到 LeftPanel。

- [ ] **Step 8: 聚类图例移入 LeftPanel**

在显示开关之后添加聚类图例。从 RightPanel（当前第 587-613 行）完整复制聚类图例代码，包括噪声聚类的特殊处理。icon 替换：

```tsx
{terrainData && terrainData.clusters.length > 0 && (
  <CollapsiblePanel title="聚类图例" icon={<Palette className="w-3.5 h-3.5" />} defaultOpen={false}>
    <div className="flex flex-col gap-1">
      {terrainData.clusters
        .filter((c) => !c.is_noise)
        .map((cluster, i) => (
          <ClusterLegendItem
            key={cluster.cluster_id}
            cluster={cluster}
            color={CLUSTER_COLORS[i % CLUSTER_COLORS.length]}
          />
        ))}
      {terrainData.clusters.find((c) => c.is_noise) && (
        <div className="flex items-center gap-2 text-xs py-1 px-2 opacity-60">
          <div
            className="w-2.5 h-2.5 rounded-full flex-shrink-0"
            style={{ backgroundColor: NOISE_COLOR }}
          />
          <span>离群</span>
          <span className="font-mono ml-auto text-[11px]">
            {terrainData.clusters.find((c) => c.is_noise)?.size}
          </span>
        </div>
      )}
    </div>
  </CollapsiblePanel>
)}
```

这是从 RightPanel 第 589-611 行的完整复制，仅 icon 从 `"🎨"` 改为 lucide 组件。

**注意**: 在 Task 11 移除 RightPanel 之前，聚类图例会暂时重复显示（左右各一份）。Task 11 会移除 RightPanel 解决此问题。

- [ ] **Step 9: Commit**

```bash
git add web/components/ui/Sidebar.tsx
git commit -m "style: LeftPanel 图标替换 + 2列指标网格 + 滑块精简 + 显示开关图标行 + 聚类图例"
```

### Task 11: Sidebar.tsx — Sidebar 顶层改为 LeftPanel + BottomToolbar

**Files:**
- Modify: `web/components/ui/Sidebar.tsx` (Sidebar 导出函数 + 新增 BottomToolbar)

- [ ] **Step 1: 修改 Sidebar 导出函数**

```tsx
export default function Sidebar() {
  return (
    <>
      <LeftPanel />
      <BottomToolbar />
    </>
  );
}
```

移除 `<RightPanel />`。`RightPanel` 函数体保留在文件中（以备参考），但不再被调用。

- [ ] **Step 2: 创建 BottomToolbar 组件**

在 Sidebar.tsx 中（Sidebar 函数之后，RightPanel 函数之前）添加：

```tsx
function BottomToolbar() {
  const {
    terrainData,
    isStaticMode,
    isLoading,
    // 历史回放
    playbackFrames, playbackIndex, isPlaying, playbackSpeed, playbackLoading, fetchProgress,
    fetchHistory, setPlaybackIndex, togglePlayback, setPlaybackSpeed, stopPlayback,
    // 聚类权重
    weightEmbedding, weightIndustry, weightNumeric, pcaTargetDim, embeddingPcaDim,
    setWeightEmbedding, setWeightIndustry, setWeightNumeric, setPcaTargetDim, setEmbeddingPcaDim,
    // 高级地形参数
    radiusScale, gridResolution, xScaleRatio, yScaleRatio,
    setRadiusScale, setGridResolution, setXScaleRatio, setYScaleRatio,
    fetchTerrain, computeProgress,
  } = useTerrainStore();

  const [activePopup, setActivePopup] = useState<"playback" | "settings" | "quality" | null>(null);

  if (!terrainData || isStaticMode) return null;

  const togglePopup = (panel: typeof activePopup) => {
    setActivePopup((prev) => (prev === panel ? null : panel));
  };

  return (
    <>
      {/* 弹出面板 */}
      <AnimatePresence>
        {activePopup && (
          <motion.div
            key={activePopup}
            initial={{ opacity: 0, y: 12, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.98 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="overlay fixed bottom-16 left-[280px] w-[360px] z-30"
          >
            <div className="glass-panel p-4 max-h-[400px] overflow-y-auto scrollbar-thin">
              {activePopup === "playback" && (
                <PlaybackPopup
                  {...{ playbackFrames, playbackIndex, isPlaying, playbackSpeed, playbackLoading, fetchProgress, isLoading }}
                  onFetchHistory={() => fetchHistory(7)}
                  onSetPlaybackIndex={setPlaybackIndex}
                  onTogglePlayback={togglePlayback}
                  onSetPlaybackSpeed={setPlaybackSpeed}
                  onStopPlayback={stopPlayback}
                />
              )}
              {activePopup === "settings" && (
                <SettingsPopup
                  {...{ weightEmbedding, weightIndustry, weightNumeric, pcaTargetDim, embeddingPcaDim,
                    radiusScale, gridResolution, xScaleRatio, yScaleRatio, isLoading, computeProgress }}
                  onSetWeightEmbedding={setWeightEmbedding}
                  onSetWeightIndustry={setWeightIndustry}
                  onSetWeightNumeric={setWeightNumeric}
                  onSetPcaTargetDim={setPcaTargetDim}
                  onSetEmbeddingPcaDim={setEmbeddingPcaDim}
                  onSetRadiusScale={setRadiusScale}
                  onSetGridResolution={(v: number) => setGridResolution(Math.round(v))}
                  onSetXScaleRatio={setXScaleRatio}
                  onSetYScaleRatio={setYScaleRatio}
                  onFetchTerrain={fetchTerrain}
                />
              )}
              {activePopup === "quality" && terrainData.cluster_quality && (
                <ClusterQualityPanel quality={terrainData.cluster_quality} />
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* 底部工具栏 */}
      <div className="overlay fixed bottom-4 left-[280px] right-4 flex justify-center z-20">
        <div className="glass-panel px-4 py-2 flex items-center gap-1">
          <button
            onClick={() => togglePopup("playback")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-smooth ${
              activePopup === "playback"
                ? "bg-[var(--accent-light)] text-[var(--accent)] font-medium"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-gray-50"
            }`}
          >
            <History className="w-3.5 h-3.5" />
            历史回放
          </button>
          <div className="w-px h-4 bg-[var(--border)]" />
          <button
            onClick={() => togglePopup("settings")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-smooth ${
              activePopup === "settings"
                ? "bg-[var(--accent-light)] text-[var(--accent)] font-medium"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-gray-50"
            }`}
          >
            <Settings2 className="w-3.5 h-3.5" />
            高级设置
          </button>
          <div className="w-px h-4 bg-[var(--border)]" />
          <button
            onClick={() => togglePopup("quality")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-smooth ${
              activePopup === "quality"
                ? "bg-[var(--accent-light)] text-[var(--accent)] font-medium"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-gray-50"
            }`}
            disabled={!terrainData.cluster_quality}
          >
            <Activity className="w-3.5 h-3.5" />
            质量
          </button>
        </div>
      </div>
    </>
  );
}
```

- [ ] **Step 3: 创建 PlaybackPopup 组件**

从原 RightPanel 的历史回放 CollapsiblePanel 内容提取，作为新的内部函数组件。内容逻辑完全保留，只移除 CollapsiblePanel 外壳，去掉 emoji：

```tsx
function PlaybackPopup({
  playbackFrames, playbackIndex, isPlaying, playbackSpeed,
  playbackLoading, fetchProgress, isLoading,
  onFetchHistory, onSetPlaybackIndex, onTogglePlayback, onSetPlaybackSpeed, onStopPlayback,
}: {
  playbackFrames: any; playbackIndex: number; isPlaying: boolean; playbackSpeed: number;
  playbackLoading: boolean; fetchProgress: any; isLoading: boolean;
  onFetchHistory: () => void; onSetPlaybackIndex: (i: number) => void;
  onTogglePlayback: () => void; onSetPlaybackSpeed: (s: number) => void; onStopPlayback: () => void;
}) {
  // 原 RightPanel 历史回放 CollapsiblePanel 内部 JSX，
  // 仅去掉 CollapsiblePanel 外壳和 emoji，保留全部控件逻辑
  // 事件处理改为调用 onXxx props
  return (
    <div className="space-y-3">
      <div className="text-xs font-medium text-[var(--text-secondary)] flex items-center gap-2">
        <History className="w-3.5 h-3.5" /> 历史回放
      </div>
      {/* 原有内容：日期显示、时间轴滑块、播放控制、速度控制、退出按钮 */}
      {/* 直接从 RightPanel 的 CollapsiblePanel "历史回放" 内部 JSX 搬入 */}
      {/* 将 fetchHistory(7) → onFetchHistory(), setPlaybackIndex → onSetPlaybackIndex, etc. */}
    </div>
  );
}
```

实现时直接将原 RightPanel 中第 443-576 行的 CollapsiblePanel 内部 JSX 搬入，去掉 emoji，将 store action 改为 prop 调用。

- [ ] **Step 4: 创建 SettingsPopup 组件**

包含原 RightPanel 聚类权重部分 + 从 LeftPanel 移出的 4 个滑块：

```tsx
function SettingsPopup({ ...props }) {
  return (
    <div className="space-y-3">
      <div className="text-xs font-medium text-[var(--text-secondary)] flex items-center gap-2">
        <Settings2 className="w-3.5 h-3.5" /> 高级设置
      </div>

      {/* 地形参数 */}
      <div className="text-[10px] text-[var(--text-tertiary)] font-medium mt-1">地形参数</div>
      <SliderControl label="核平滑半径" value={props.radiusScale} min={0.1} max={6.0} step={0.1}
        onChange={props.onSetRadiusScale} displayValue={`×${props.radiusScale.toFixed(1)}`}
        hint="越小越尖锐·越大越平滑" />
      <SliderControl label="网格分辨率" value={props.gridResolution} min={64} max={1024} step={64}
        onChange={props.onSetGridResolution} displayValue={`${props.gridResolution}×${props.gridResolution}`}
        hint="越高越精细·计算越慢" />
      <SliderControl label="X 轴比例" value={props.xScaleRatio} min={0.3} max={3.0} step={0.05}
        onChange={props.onSetXScaleRatio} displayValue={`×${props.xScaleRatio.toFixed(2)}`} />
      <SliderControl label="Y 轴比例" value={props.yScaleRatio} min={0.3} max={3.0} step={0.05}
        onChange={props.onSetYScaleRatio} displayValue={`×${props.yScaleRatio.toFixed(2)}`} />

      {/* 聚类权重 */}
      <div className="text-[10px] text-[var(--text-tertiary)] font-medium mt-2 pt-2 border-t border-[var(--border)]">聚类权重</div>
      <SliderControl label="嵌入权重" value={props.weightEmbedding} min={0} max={3} step={0.1}
        onChange={props.onSetWeightEmbedding} displayValue={props.weightEmbedding.toFixed(1)}
        hint="BGE 语义嵌入层权重" />
      <SliderControl label="行业权重" value={props.weightIndustry} min={0} max={2} step={0.1}
        onChange={props.onSetWeightIndustry} displayValue={props.weightIndustry.toFixed(1)}
        hint="行业 one-hot 层权重" />
      <SliderControl label="数值权重" value={props.weightNumeric} min={0} max={3} step={0.1}
        onChange={props.onSetWeightNumeric} displayValue={props.weightNumeric.toFixed(1)}
        hint="财务/交易特征层权重" />
      <SliderControl label="PCA 维度" value={props.pcaTargetDim} min={10} max={100} step={5}
        onChange={props.onSetPcaTargetDim} displayValue={props.pcaTargetDim.toString()}
        hint="最终降维目标维度" />
      <SliderControl label="嵌入 PCA" value={props.embeddingPcaDim} min={8} max={64} step={4}
        onChange={props.onSetEmbeddingPcaDim} displayValue={props.embeddingPcaDim.toString()}
        hint="嵌入预降维维度" />

      {/* 应用按钮 */}
      <button
        onClick={props.onFetchTerrain}
        disabled={props.isLoading}
        className="btn-primary w-full mt-2 text-xs"
      >
        {props.isLoading ? (
          <span className="flex items-center justify-center gap-1.5">
            <Spinner />
            {props.computeProgress
              ? `${props.computeProgress.step}/${props.computeProgress.totalSteps} ${props.computeProgress.stepName}`
              : "连接服务器..."}
          </span>
        ) : "应用并重算"}
      </button>
    </div>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add web/components/ui/Sidebar.tsx
git commit -m "style: Sidebar 布局重组 — 单左侧栏 + BottomToolbar + 弹出面板"
```

### Task 12: 全局验证 + 清理

**Files:**
- All modified files

- [ ] **Step 1: 启动开发服务器验证**

Run: `cd web && npm run dev`

在浏览器中验证：
1. 毛玻璃面板有内发光和 border-top 高光效果
2. 背景有冷暖渐变（不是纯色）
3. 所有图标已替换为 lucide 单色图标（无 emoji）
4. 左侧栏精简，Z 轴指标 2 列排列
5. 显示开关是 5 个图标按钮
6. 底部浮动工具栏显示 3 个按钮
7. 点击工具栏按钮弹出面板（带动画）
8. AI 聊天面板有退出动画
9. TopBar 延伸到右侧（不留 260px 空间）
10. 搜索框有 ⌘K 装饰
11. 无浏览器控制台报错

- [ ] **Step 2: 构建检查**

Run: `cd web && npm run build`

确认无 TypeScript 编译错误。

- [ ] **Step 3: 清理 RightPanel 死代码（可选）**

如果确认一切正常，可以删除 `RightPanel` 函数体（或加 `// @deprecated — 已重构到 BottomToolbar` 注释保留）。

- [ ] **Step 4: Final commit**

```bash
git add -A web/
git commit -m "style: 前端视觉美化完成 — 毛玻璃精炼 + Lucide图标 + 单侧栏布局 + 底部工具栏"
```
