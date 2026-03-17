# 板块排行修复 + 独立任务管理页面 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复板块排行的3个问题（滚动、去重、点击报错），并将定时任务从 Expert 弹出面板改为独立 /tasks 页面

**Architecture:** 板块修复是纯 bug fix + UI 调整；任务管理页面是将现有 scheduler 后端路由保持不变，前端新建独立页面 + 从 expert 页面解耦

**Tech Stack:** Next.js, Zustand, FastAPI, lightweight-charts v5, APScheduler

---

## Part A: 板块排行修复

### Task 1: 板块排行表改为固定高度滚动

**Files:**
- Modify: `frontend/components/sector/SectorDashboard.tsx`
- Modify: `frontend/components/sector/SectorRankTable.tsx`

**改动:**
- SectorDashboard 上半区 grid 移除 `minHeight: 400`，改为固定 `h-[calc(50vh-60px)]`
- SectorRankTable 内部表格容器加 `overflow-y-auto` 配合父级固定高度

### Task 2: 后端板块数据去重

**Files:**
- Modify: `backend/engine/sector/engine.py` (_fetch_boards)

**改动:**
- 在 `_fetch_boards` 遍历 `board_list_df` 时，按 `board_name` 去重（只保留第一个出现的）
- 东方财富 API 返回的"银行Ⅰ"、"银行Ⅱ"等分级板块，数据相同但 board_code 不同，保留第一个即可

### Task 3: 修复前端点击板块报错

**Files:**
- Modify: `frontend/components/sector/SectorTrendChart.tsx`
- Modify: `frontend/stores/useSectorStore.ts`

**改动:**
- SectorTrendChart 的 klineData time 格式问题：`item.date` 可能包含时间戳，需要确保是 `YYYY-MM-DD` 格式
- loadDetail 增加 try-catch 和空数据兜底
- lightweight-charts v5 的 time 格式要求严格，需要确保数据排序正确且无重复日期

## Part B: 独立任务管理页面

### Task 4: 创建 /tasks 页面

**Files:**
- Create: `frontend/app/tasks/page.tsx`
- Modify: `frontend/components/ui/NavSidebar.tsx`（新增导航入口）

### Task 5: 改造任务管理组件为全页面布局

**Files:**
- Create: `frontend/components/tasks/TaskManager.tsx`（全页面任务管理器）
- Create: `frontend/components/tasks/TaskCard.tsx`（任务卡片）
- Create: `frontend/components/tasks/CreateTaskDialog.tsx`（创建任务表单）
- Create: `frontend/components/tasks/TaskHistory.tsx`（任务执行历史）
- Move/Adapt: `frontend/stores/useSchedulerStore.ts`（保持不变，两处复用）
- Move/Adapt: `frontend/types/scheduler.ts`（保持不变）

### Task 6: 从 Expert 页面移除 ScheduledTasks 面板

**Files:**
- Modify: `frontend/app/expert/page.tsx`（移除 ScheduledTasksPanel import 和使用）
