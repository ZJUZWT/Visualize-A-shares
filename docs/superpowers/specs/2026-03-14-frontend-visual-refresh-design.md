# StockTerrain 前端纯视觉层美化设计

**日期**: 2026-03-14
**状态**: 已确认
**范围**: 纯视觉层 — 只改 CSS/样式/图标/布局，不动数据接口和类型定义

## 背景

当前前端存在以下视觉问题：
- 左右两侧面板信息密度过高，控件堆叠需要大量滚动
- 大量 emoji 作为 UI 图标，跨平台渲染不一致，视觉风格不统一
- 毛玻璃面板可以更精致（缺少内发光、方向性阴影）
- 背景为纯色 `#EEF2F7`，缺乏深度
- 过渡动画使用 Material Design 标准曲线，缺少高端感
- 面板缺少退出动画（只有入场）

另一个 Claude Code 正在修改后端聚类引擎，前后端接口可能变动，因此本次**不触碰任何数据接口、TypeScript 类型定义或渲染逻辑**。

## 设计决策

| 决策项 | 选择 |
|--------|------|
| 视觉风格 | A+B 混搭：Apple visionOS 毛玻璃 + Linear/Vercel 极简排版 |
| 布局结构 | 单左侧栏 + 底部浮动工具栏（取消右侧常驻面板） |
| 改造深度 | 纯视觉层，不动数据接口 |
| 图标系统 | Emoji → lucide-react（已安装但未使用） |

## 改动范围

### 改动文件
- `web/app/globals.css` — 配色、毛玻璃、阴影、过渡曲线
- `web/app/page.tsx` — 移除 `bg-[#EEF2F7]` 改为 `bg-transparent`、版本号改为 `v3.1`
- `web/components/ui/Sidebar.tsx` — 布局重组、图标替换、精简控件、新增底部浮动工具栏
- `web/components/ui/TopBar.tsx` — 搜索框样式美化（保持 always-visible input，仅视觉调整）
- `web/components/ui/AIChatPanel.tsx` — 图标替换、样式微调
- `web/components/ui/RelatedStocksPanel.tsx` — 图标替换

### 不动的部分
- TypeScript 接口/类型定义（`StockPoint`, `TerrainData`, `Z_METRIC_ICONS` 类型签名等）— 等后端稳定
- `web/types/terrain.ts` — **不改此文件**，`Z_METRIC_ICONS` 保持 `Record<ZMetric, string>` 类型不变
- 数据获取逻辑（`useTerrainStore` 的 fetch/SSE）— 不改接口调用
- `(stock as any)` 类型强转 — 需等后端字段确定
- `StockNodes.tsx` 渲染逻辑/着色逻辑 — 功能正常不动
- `TerrainMesh.tsx` 着色器代码 — 功能正常不动
- 不新增 npm 依赖（不引入 shadcn/ui，留给后续重构）

## 模块 ① — globals.css 配色与基础样式

### glass-panel 精炼

```css
/* 改前 */
.glass-panel {
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(20px) saturate(1.4);
  border: 1px solid rgba(232, 236, 244, 0.8);
  border-radius: var(--radius);
  box-shadow: var(--shadow-md);
}

/* 改后 */
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

关键变化：降低不透明度（0.88→0.82）增加通透感，增加 `border-top` 高光模拟光源，`inset` 阴影增加立体感。

### Canvas 渐变背景

```css
.canvas-container {
  background: radial-gradient(
    ellipse at 30% 20%,
    #EEF4FF 0%,
    #F8FAFE 40%,
    #FDF8F5 70%,
    #F5F7FA 100%
  );
}
```

冷暖双色径向渐变，给 3D 场景一个自然光照环境感。

**注意**: `page.tsx` 中 `<main>` 的 `bg-[#EEF2F7]` 需同步改为 `bg-transparent`，否则内联样式会覆盖 CSS 渐变。

### 阴影系统

```css
:root {
  --shadow-xs: 0 1px 2px rgba(0, 0, 0, 0.03);
  --shadow-sm: 0 2px 4px -1px rgba(0, 0, 0, 0.04);
  --shadow-md: 0 4px 12px -2px rgba(0, 0, 0, 0.06);
  --shadow-lg: 0 8px 24px -4px rgba(0, 0, 0, 0.08);
  --shadow-xl: 0 16px 48px -8px rgba(0, 0, 0, 0.10);
}
```

负 spread 值让阴影不扩散到四周，只向下，更自然。

### 过渡曲线

```css
:root {
  --ease-out-expo: cubic-bezier(0.16, 1, 0.3, 1);
}

.transition-smooth {
  transition: all 0.25s var(--ease-out-expo);
}
```

sharp start + gentle end = 干脆利落的感觉。

**注意**: `transition-smooth` 是全局类，被 Sidebar、TopBar、RelatedStocksPanel 等多处使用。修改后需全局验证所有 hover/过渡效果，确保无回归。

### 按钮圆角统一

- 面板/卡片: `--radius: 12px`（从 14px 微调）
- 按钮/输入框: `border-radius: 8px`（统一），修改 `.btn-primary` 和 `.btn-secondary` 的 `border-radius: 10px` → `8px`

### 配色微调

```css
:root {
  --green-stock: #10B981;  /* 从 #22C55E 改为 emerald，更柔和 */
  --text-primary: #0F172A; /* 从 #1A1D26 加深，对比度更好 */
}
```

## 模块 ② — Emoji → Lucide 图标替换

全部从 `lucide-react` 导入，统一尺寸 `w-3.5 h-3.5`。

**重要**: `terrain.ts` 中的 `Z_METRIC_ICONS`（`Record<ZMetric, string>`）**不修改**，保持原有 emoji 字符串类型不变。在 `Sidebar.tsx` 中新建本地映射 `METRIC_ICON_COMPONENTS` 覆盖渲染，不动 `terrain.ts` 的类型签名。

### Sidebar.tsx

在文件顶部导入 lucide 图标，并定义本地映射：

```tsx
import {
  BarChart3, Mountain, FileText, Eye, Settings2, History,
  Activity, Palette, TrendingUp, RefreshCw, DollarSign,
  BookOpen, Scale, Sparkles, Tag, Grid3x3, Waves, Minimize2, GripVertical,
} from "lucide-react";
import type { ZMetric } from "@/types/terrain";

// 本地图标映射，覆盖 terrain.ts 中的 emoji Z_METRIC_ICONS
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

CollapsiblePanel icon 属性改为接收 `ReactNode`（目前已经是 `string`，改为也支持 JSX）：

| 位置 | 原 Emoji | 替换为 |
|------|---------|--------|
| CollapsiblePanel "Z 轴指标" | `📊` | `<BarChart3 className="w-3.5 h-3.5" />` |
| CollapsiblePanel "地形控制" | `🏔️` | `<Mountain className="w-3.5 h-3.5" />` |
| CollapsiblePanel "数据概览" | `📋` | `<FileText className="w-3.5 h-3.5" />` |
| CollapsiblePanel "显示选项" | `👁️` | `<Eye className="w-3.5 h-3.5" />` |
| CollapsiblePanel "聚类权重" | `⚙️` | `<Settings2 className="w-3.5 h-3.5" />` |
| CollapsiblePanel "历史回放" | `📅` | `<History className="w-3.5 h-3.5" />` |
| CollapsiblePanel "聚类质量" | `📊` | `<Activity className="w-3.5 h-3.5" />` |
| CollapsiblePanel "聚类图例" | `🎨` | `<Palette className="w-3.5 h-3.5" />` |
| 按钮 "生成 3D 地形" | `🏔️` | 移除 emoji，纯文字 |
| 按钮 "刷新地形数据" | `🔄` | 移除 emoji，纯文字 |
| 按钮 "应用并重算" | `🏔️` | 移除 emoji，纯文字 |
| 按钮 "加载历史回放" | `📅` | 移除 emoji，纯文字 |
| 静态模式提示 | `📸` | 移除 emoji |
| 错误提示 | `❌` | 移除 emoji |

Z 轴指标按钮中的 emoji 图标替换为 `METRIC_ICON_COMPONENTS[key]` 渲染：
```tsx
const IconComp = METRIC_ICON_COMPONENTS[key];
<IconComp className="w-3.5 h-3.5" />
```

CollapsiblePanel 的 `icon` prop 类型从 `string` 改为 `React.ReactNode`，渲染时直接输出（不再包裹在 `<span>` 中以 emoji 方式显示）。

### AIChatPanel.tsx

| 位置 | 原 Emoji | 替换为 |
|------|---------|--------|
| 浮动按钮 | `🤖` / `✕` | `<MessageCircle>` / `<X>` |
| 面板标题 | `🤖` | `<MessageCircle>` |
| 空状态无 Key | `🔑` | `<Key>` |
| 空状态有 Key | `🤖` | `<Sparkles>` |
| 建议按钮前缀 | `💡` | `<Lightbulb>` |
| 显示/隐藏密码 | `🙈`/`👁️` | `<EyeOff>`/`<Eye>` |
| 保存按钮 | `✓` | 纯文字 "保存配置" |
| 提示信息 | `💡`/`📡` | 移除 emoji |

### RelatedStocksPanel.tsx

| 位置 | 原 Emoji | 替换为 |
|------|---------|--------|
| 标题 | `🔗` | `<Link>` |
| 已选中标记 | `📌` | `<Pin>` |

### terrain.ts — Z_METRIC_LABELS

仅修改 `rise_prob` 的标签值，移除 emoji 前缀：

```typescript
// 改前
rise_prob: "🔮 明日上涨概率",
// 改后
rise_prob: "明日上涨概率",
```

`Z_METRIC_ICONS` 保持不变（类型签名不动）。

## 模块 ③ — 布局重组

### 组件结构

布局重组仅在 `Sidebar.tsx` 内完成。当前 `Sidebar` 组件渲染 `<LeftPanel />` 和 `<RightPanel />`。改为：

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

- `RightPanel` 函数保留但不再在顶层渲染，其内容拆散到 `LeftPanel` 和 `BottomToolbar` 的弹出面板中。
- `BottomToolbar` 是 `Sidebar.tsx` 内的新函数组件（不新建文件）。

### TopBar 定位调整

移除 RightPanel 后，TopBar 的 `right-[260px]` 改为 `right-4`（不再需要为右侧面板留空间）。

### 左侧栏（LeftPanel）

宽度保持 260px。内容精简为：

1. **Logo 区** — 保持不变，版本号改为 `v3.1`
2. **操作按钮** — 生成/刷新按钮 + 进度条（不变）
3. **Z 轴指标** — 改为 2 列网格布局（`grid grid-cols-2 gap-1`），更紧凑
4. **视图控制** — 只保留「高度缩放」和「XY 整体缩放」两个核心滑块。其余滑块（核平滑半径、网格分辨率、X 轴比例、Y 轴比例）移入底部栏"高级设置"弹出面板
5. **显示开关** — 改为图标按钮行（5 个方块），使用以下 lucide 图标：
   - 股票标签 → `<Tag>` (tooltip: "股票标签")
   - 底部网格 → `<Grid3x3>` (tooltip: "底部网格")
   - 等高线 → `<Waves>` (tooltip: "等高线")
   - 球体拍平 → `<Minimize2>` (tooltip: "球体拍平")
   - 价格垂线 → `<GripVertical>` (tooltip: "价格垂线")
   - Tooltip 实现：CSS `title` 属性（原生 tooltip，不引入额外组件）
   - 激活态：`bg-[var(--accent-light)] text-[var(--accent)]`
   - 未激活态：`bg-gray-50 text-[var(--text-tertiary)]`
6. **聚类图例** — 紧凑排列（保持现有 ClusterLegendItem，默认折叠）

### 底部浮动工具栏（BottomToolbar）

```
┌─────────────────────────────────────────────┐
│   ⏮ 历史回放  │  ⚙ 高级设置  │  📊 质量   │
└─────────────────────────────────────────────┘
```

- 位置: `fixed bottom-4 left-[280px] right-4`，水平居中用 `flex justify-center`
- 样式: `glass-panel` 毛玻璃，`px-4 py-2`
- 三个按钮用 lucide 图标 + 文字，用 `|` 分隔符或 `gap` 间隔
- 仅在 `terrainData` 存在且 `!isStaticMode` 时显示
- 图标: `<History>` 历史回放 / `<Settings2>` 高级设置 / `<Activity>` 质量
- 每次只能打开一个弹出面板（单选行为）：state 为 `activePopup: "playback" | "settings" | "quality" | null`
- 点击已激活的按钮关闭面板，点击其他按钮切换面板

### 弹出面板

- 从底部工具栏上方出现，`fixed bottom-16 left-[280px]`，宽度 `w-[360px]`
- 样式: `glass-panel` 毛玻璃
- 动画: 使用 framer-motion `AnimatePresence`（见模块④ 注意事项）
- 三个面板内容：
  - **历史回放**: 原 RightPanel 的历史回放 CollapsiblePanel 内容（日期显示、时间轴滑块、播放控制、速度控制、退出回放按钮）
  - **高级设置**: 原 RightPanel 的聚类权重 + 从 LeftPanel 移出的滑块（核平滑半径、网格分辨率、X轴比例、Y轴比例）+ "应用并重算"按钮
  - **质量**: 原 RightPanel 的 ClusterQualityPanel

## 模块 ④ — 细节打磨

### CollapsiblePanel 面板头

```
/* 改前 */
text-[11px] font-semibold text-[var(--text-tertiary)] uppercase tracking-wider

/* 改后 */
text-xs font-medium text-[var(--text-secondary)]
```

去掉 uppercase 和 tracking-wider，更轻盈。

### AnimatePresence 退出动画

`framer-motion` 已安装（`^11.0.0`）但当前代码库中**从未导入使用过**。实现时需注意：
- 先在一个简单组件（如 AIChatPanel 的面板显隐）上验证 `AnimatePresence` 在 React 19 + Next.js 15 下工作正常
- 确认无 SSR hydration 问题（所有使用处均为 `"use client"` 组件，应无问题）
- 验证通过后再推广到其他面板

应用到以下面板的显隐：

```tsx
import { AnimatePresence, motion } from "framer-motion";

<AnimatePresence>
  {isOpen && (
    <motion.div
      initial={{ opacity: 0, y: 12, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 8, scale: 0.98 }}
      transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
    >
      ...
    </motion.div>
  )}
</AnimatePresence>
```

应用位置：
- AIChatPanel 聊天窗口（替换现有的 CSS `animate-in`）
- BottomToolbar 弹出面板
- TopBar 搜索结果下拉

### TopBar 搜索框样式

**不改交互逻辑**（保持 always-visible input），只做视觉调整：
- 搜索图标替换为 lucide `<Search>`
- 关闭按钮替换为 lucide `<X>`
- 在输入框右侧添加 `<kbd>` 快捷键提示：`<kbd className="...">⌘K</kbd>`（仅作为视觉装饰，不绑定键盘事件，键盘快捷键留给 Roadmap）

### page.tsx 修改

1. `<main>` 的 `bg-[#EEF2F7]` 改为 `bg-transparent`
2. 底部版权区 `StockTerrain v2.0` 改为 `StockTerrain v3.1`

## Roadmap（后续等后端稳定后）

- [ ] 引入 shadcn/ui 组件库（Slider、Switch、Command、Select）
- [ ] 消除 `(stock as any)` 类型强转，对齐后端字段
- [ ] `Z_METRIC_ICONS` 类型从 `string` 改为 React 组件类型（需后端字段稳定后统一处理）
- [ ] 抽取球体着色逻辑为共享函数
- [ ] computeTargetY 加入 dirty flag 优化
- [ ] WebGL 降级方案
- [ ] 键盘快捷键系统（Cmd+K 搜索、Cmd+/ AI 聊天、Escape 关闭面板）
- [ ] SSE 重连/超时逻辑
- [ ] 无障碍：ARIA labels、焦点管理
