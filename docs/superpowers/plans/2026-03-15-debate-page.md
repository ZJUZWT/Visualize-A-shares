# 专家辩论页面 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增专家辩论前端页面 `/debate`，含左侧导航栏、多头 vs 空头左右对立布局、SSE 实时流、裁判揭幕动画、历史回放。

**Architecture:** 后端新增两个 REST 接口（history + replay）；前端新建 zustand store 管理 SSE 状态，9 个 React 组件分层组合，NavSidebar 以 fixed 定位插入两个页面。

**Tech Stack:** Next.js 15, React 19, Tailwind CSS v4, framer-motion, lucide-react, zustand 5, FastAPI SSE (fetch + ReadableStream)

---

## Chunk 1: 后端 — 历史与回放接口

### Task 1: 新增 `GET /api/v1/debate/history` 和 `GET /api/v1/debate/{debate_id}`

**Files:**
- Modify: `engine/api/routes/debate.py`
- Test: `engine/tests/test_debate_history_routes.py`

**背景：** `shared.debate_records` 表由 `agent/debate.py` 的 `persist_debate()` 写入，主键列名为 `id`（存储值为 `debate_id` 字符串如 `600519_20260315143022`）。`signal` 和 `debate_quality` 存在 `judge_verdict_json` JSON blob 中，需用 DuckDB JSON 函数提取。

- [ ] **Step 1: 写失败测试**

```python
# engine/tests/test_debate_history_routes.py
import json
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from main import app
    return TestClient(app)

def test_history_returns_list(client):
    resp = client.get("/api/v1/debate/history?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)

def test_history_item_schema(client):
    """如果有记录，验证字段结构"""
    resp = client.get("/api/v1/debate/history?limit=1")
    data = resp.json()
    if data:
        item = data[0]
        assert "debate_id" in item
        assert "target" in item
        assert "created_at" in item

def test_replay_not_found(client):
    resp = client.get("/api/v1/debate/nonexistent_id")
    assert resp.status_code == 404

def test_replay_schema(client):
    """先查 history，再用第一条 id 查 replay"""
    hist = client.get("/api/v1/debate/history?limit=1").json()
    if not hist:
        pytest.skip("无辩论记录，跳过")
    debate_id = hist[0]["debate_id"]
    resp = client.get(f"/api/v1/debate/{debate_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "blackboard_json" in data
    assert "judge_verdict_json" in data
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd engine && python -m pytest tests/test_debate_history_routes.py -v
```

期望: `FAILED` — `404 Not Found`（路由不存在）

- [ ] **Step 3: 实现两个接口**

在 `engine/api/routes/debate.py` 末尾追加：

```python
from fastapi import Query


@router.get("/debate/history")
async def get_debate_history(limit: int = Query(default=20, ge=1, le=100)):
    """返回最近 N 条辩论记录摘要"""
    try:
        from data_engine import get_data_engine
        con = get_data_engine().store._conn

        # 检查表是否存在
        tables = con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='shared' AND table_name='debate_records'"
        ).fetchall()
        if not tables:
            return []

        rows = con.execute("""
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
        """, [limit]).fetchall()

        cols = ["debate_id", "target", "rounds_completed", "termination_reason",
                "created_at", "signal", "debate_quality"]
        return [dict(zip(cols, row)) for row in rows]
    except Exception as e:
        logger.error(f"查询辩论历史失败: {e}")
        return []


@router.get("/debate/{debate_id}")
async def get_debate_record(debate_id: str):
    """返回单条辩论完整记录（用于回放）"""
    try:
        from data_engine import get_data_engine
        con = get_data_engine().store._conn

        row = con.execute(
            "SELECT id, target, blackboard_json, judge_verdict_json, "
            "rounds_completed, termination_reason, created_at "
            "FROM shared.debate_records WHERE id = ?",
            [debate_id]
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"辩论记录不存在: {debate_id}")

        cols = ["debate_id", "target", "blackboard_json", "judge_verdict_json",
                "rounds_completed", "termination_reason", "created_at"]
        return dict(zip(cols, row))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询辩论记录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd engine && python -m pytest tests/test_debate_history_routes.py -v
```

期望: `PASSED` — 4 tests

- [ ] **Step 5: 提交**

```bash
git add engine/api/routes/debate.py engine/tests/test_debate_history_routes.py
git commit -m "feat: 新增辩论历史和回放 REST 接口"
```

---

## Chunk 4: NavSidebar + 导航集成

### Task 4: `NavSidebar` 组件 + 改动现有页面

**Files:**
- Create: `web/components/ui/NavSidebar.tsx`
- Modify: `web/app/page.tsx`
- Create: `web/app/debate/page.tsx` (空壳，后续填充)

**背景：** NavSidebar 使用 `position: fixed` 左边缘，`z-index: 50`，不影响地形页现有 fixed 覆盖层。收起 48px / hover 展开 180px，CSS transition。

- [ ] **Step 1: 创建 NavSidebar**

```tsx
// web/components/ui/NavSidebar.tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Mountain, Scale } from "lucide-react";

const NAV_ITEMS = [
  { href: "/", icon: Mountain, label: "地形图" },
  { href: "/debate", icon: Scale, label: "专家辩论" },
];

export default function NavSidebar() {
  const pathname = usePathname();

  return (
    <nav
      className="nav-sidebar fixed left-0 top-0 h-screen z-50 flex flex-col py-4 gap-1
                 bg-[var(--bg-secondary)] border-r border-[var(--border)]
                 overflow-hidden"
      style={{ width: 48 }}
    >
      {/* Logo */}
      <div className="flex items-center justify-center h-10 mb-2 shrink-0">
        <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-[#4F8EF7] to-[#7B68EE]
                        flex items-center justify-center text-white text-xs font-bold">
          T
        </div>
        <span className="nav-label ml-2 text-sm font-semibold text-[var(--text-primary)] whitespace-nowrap opacity-0">
          StockTerrain
        </span>
      </div>

      {NAV_ITEMS.map(({ href, icon: Icon, label }) => {
        const active = pathname === href;
        return (
          <Link
            key={href}
            href={href}
            className={`nav-item flex items-center gap-3 mx-2 px-2 py-2 rounded-lg
                        transition-colors duration-150 shrink-0
                        ${active
                          ? "bg-[var(--accent-light)] text-[var(--accent)]"
                          : "text-[var(--text-secondary)] hover:bg-[var(--bg-primary)] hover:text-[var(--text-primary)]"
                        }`}
          >
            <Icon size={18} className="shrink-0" />
            <span className="nav-label text-sm font-medium whitespace-nowrap opacity-0">
              {label}
            </span>
          </Link>
        );
      })}

      <style jsx>{`
        .nav-sidebar {
          transition: width 200ms cubic-bezier(0.16, 1, 0.3, 1);
        }
        .nav-sidebar:hover {
          width: 180px !important;
        }
        .nav-sidebar:hover .nav-label {
          opacity: 1;
          transition: opacity 150ms ease 80ms;
        }
        .nav-label {
          transition: opacity 100ms ease;
        }
      `}</style>
    </nav>
  );
}
```

- [ ] **Step 2: 改动 `web/app/page.tsx`**

在文件顶部 import 列表中加入：

```tsx
import NavSidebar from "@/components/ui/NavSidebar";
```

在 `<main>` 标签内第一行插入 `<NavSidebar />`，并给 `<main>` 加 `ml-12`：

```tsx
// 修改前:
<main className="relative w-screen h-screen overflow-hidden bg-transparent">
  {/* Layer 0: 3D 场景 */}

// 修改后:
<main className="relative w-screen h-screen overflow-hidden bg-transparent ml-12">
  <NavSidebar />
  {/* Layer 0: 3D 场景 */}
```

- [ ] **Step 3: 创建辩论页空壳**

```tsx
// web/app/debate/page.tsx
"use client";

import NavSidebar from "@/components/ui/NavSidebar";

export default function DebatePage() {
  return (
    <main className="relative w-screen h-screen overflow-hidden bg-[var(--bg-primary)] ml-12">
      <NavSidebar />
      <div className="flex items-center justify-center h-full">
        <p className="text-[var(--text-tertiary)]">辩论页面加载中...</p>
      </div>
    </main>
  );
}
```

- [ ] **Step 4: 验证导航**

启动前端：`cd web && npm run dev`

访问 `http://localhost:3000`，确认：
- 左侧出现 48px 导航栏
- hover 展开到 180px，显示"地形图"和"专家辩论"文字
- 点击"专家辩论"跳转到 `/debate`，显示占位文字
- 点击"地形图"返回 `/`，地形页正常

- [ ] **Step 5: 提交**

```bash
git add web/components/ui/NavSidebar.tsx web/app/page.tsx web/app/debate/page.tsx
git commit -m "feat: NavSidebar 导航栏 + 辩论页路由空壳"
```

---

## Chunk 2: 前端类型定义

### Task 2: `web/types/debate.ts`

**Files:**
- Create: `web/types/debate.ts`

**背景：** 前端类型与后端 `agent/schemas.py` 的 Pydantic 模型对应。`DebateEntry` 中 `data_requests[].result` 类型不定，前端用 `unknown` 并忽略。

- [ ] **Step 1: 创建类型文件**

```typescript
// web/types/debate.ts

export type DebateSignal = "bullish" | "bearish" | "neutral";
export type DebateQuality = "consensus" | "strong_disagreement" | "one_sided";
export type DebateStatus = "idle" | "debating" | "final_round" | "judging" | "completed";
export type Stance = "insist" | "partial_concede" | "concede";

export interface DebateEntry {
  role: string;
  round: number;
  stance: Stance | null;
  speak: boolean;
  argument: string;
  challenges: string[];
  confidence: number;
  retail_sentiment_score: number | null;
  // data_requests 前端不渲染，忽略
}

export interface JudgeVerdict {
  target: string;
  debate_id: string;
  summary: string;
  signal: DebateSignal | null;
  score: number | null;
  key_arguments: string[];
  bull_core_thesis: string;
  bear_core_thesis: string;
  retail_sentiment_note: string;
  smart_money_note: string;
  risk_warnings: string[];
  debate_quality: DebateQuality;
  termination_reason: string;
  timestamp: string;
}

export interface DebateHistoryItem {
  debate_id: string;
  target: string;
  signal: DebateSignal | null;
  debate_quality: DebateQuality | null;
  rounds_completed: number;
  termination_reason: string;
  created_at: string;
}

export interface DebateReplayRecord {
  debate_id: string;
  target: string;
  blackboard_json: string;
  judge_verdict_json: string;
  rounds_completed: number;
  termination_reason: string;
  created_at: string;
}

// SSE 事件 payload 类型
export interface DebateStartPayload {
  debate_id: string;
  target: string;
  max_rounds: number;
  participants: string[];
}

export interface DebateRoundStartPayload {
  round: number;
  is_final: boolean;
}

export interface DebateEndPayload {
  reason: string;
  rounds_completed: number;
}

// 观察员状态（ObserverBar 用）
export interface ObserverState {
  speak: boolean;
  argument: string;
  retail_sentiment_score?: number;
}

// 角色状态（RoleCard 用）
export interface RoleState {
  stance: Stance | null;
  confidence: number;
  conceded: boolean;
}
```

- [ ] **Step 2: 提交**

```bash
git add web/types/debate.ts
git commit -m "feat: 辩论页面前端类型定义"
```

---

## Chunk 3: Zustand Store + SSE 逻辑

### Task 3: `web/stores/useDebateStore.ts`

**Files:**
- Create: `web/stores/useDebateStore.ts`

**背景：**
- SSE 必须用 `fetch` + `ReadableStream`，直连 `NEXT_PUBLIC_API_BASE`（同 `useTerrainStore` 的 `SSE_API_BASE`）
- 观察员沉默推断：收到 `debate_round_start` 时，将上一轮未发言的观察员标记为 `speak: false`
- `status` 转换：`idle` → `debating` → `final_round`（is_final=true 时）→ `judging`（debate_end 后）→ `completed`（judge_verdict 后）

- [ ] **Step 1: 创建 store**

```typescript
// web/stores/useDebateStore.ts
import { create } from "zustand";
import type {
  DebateEntry, JudgeVerdict, DebateStatus,
  ObserverState, RoleState, DebateReplayRecord,
} from "@/types/debate";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

// 发言流中的条目（含系统消息）
export type TranscriptItem =
  | { type: "entry"; data: DebateEntry }
  | { type: "round_divider"; round: number; is_final: boolean }
  | { type: "system"; text: string }
  | { type: "loading"; id: string };

interface DebateStore {
  status: DebateStatus;
  transcript: TranscriptItem[];
  observerState: Record<string, ObserverState>;
  roleState: Record<string, RoleState>;
  currentRound: number;
  judgeVerdict: JudgeVerdict | null;
  isReplayMode: boolean;
  error: string | null;
  // 当前轮次各观察员是否已发言（用于推断沉默）
  _observerSpokenThisRound: Record<string, boolean>;

  startDebate: (code: string, maxRounds: number) => Promise<void>;
  loadReplay: (debateId: string) => Promise<void>;
  reset: () => void;
}

const INITIAL_ROLE_STATE: RoleState = { stance: null, confidence: 0.5, conceded: false };
const OBSERVERS = ["retail_investor", "smart_money"];
const DEBATERS = ["bull_expert", "bear_expert"];

export const useDebateStore = create<DebateStore>((set, get) => ({
  status: "idle",
  transcript: [],
  observerState: {},
  roleState: {},
  currentRound: 0,
  judgeVerdict: null,
  isReplayMode: false,
  error: null,
  _observerSpokenThisRound: {},

  reset: () => set({
    status: "idle",
    transcript: [],
    observerState: {},
    roleState: {},
    currentRound: 0,
    judgeVerdict: null,
    isReplayMode: false,
    error: null,
    _observerSpokenThisRound: {},
  }),

  startDebate: async (code, maxRounds) => {
    get().reset();
    set({ status: "debating" });

    try {
      const res = await fetch(`${API_BASE}/api/v1/debate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code, max_rounds: maxRounds }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        set({ error: err.detail ?? "请求失败", status: "idle" });
        return;
      }

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // 按 SSE 块分割（\n\n）
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() ?? "";

        for (const chunk of chunks) {
          const lines = chunk.split("\n");
          let eventType = "";
          let dataStr = "";
          for (const line of lines) {
            if (line.startsWith("event: ")) eventType = line.slice(7).trim();
            if (line.startsWith("data: ")) dataStr = line.slice(6).trim();
          }
          if (!eventType || !dataStr) continue;

          try {
            const data = JSON.parse(dataStr);
            _handleSSEEvent(eventType, data, set, get);
          } catch {
            // 忽略解析失败的事件
          }
        }
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "连接失败";
      set({ error: msg, status: "idle" });
    }
  },

  loadReplay: async (debateId) => {
    get().reset();
    set({ isReplayMode: true });

    try {
      const res = await fetch(`${API_BASE}/api/v1/debate/${debateId}`);
      if (!res.ok) {
        set({ error: "加载回放失败", isReplayMode: false });
        return;
      }
      const record: DebateReplayRecord = await res.json();
      const blackboard = JSON.parse(record.blackboard_json);
      const verdict: JudgeVerdict = JSON.parse(record.judge_verdict_json);

      // 重建发言流
      const transcript: TranscriptItem[] = [];
      let lastRound = 0;
      for (const entry of (blackboard.transcript ?? []) as DebateEntry[]) {
        if (entry.round !== lastRound) {
          transcript.push({ type: "round_divider", round: entry.round, is_final: false });
          lastRound = entry.round;
        }
        if (DEBATERS.includes(entry.role)) {
          transcript.push({ type: "entry", data: entry });
        }
      }

      // 重建角色状态（取最后一条发言）
      const roleState: Record<string, RoleState> = {};
      for (const entry of (blackboard.transcript ?? []) as DebateEntry[]) {
        if (DEBATERS.includes(entry.role)) {
          roleState[entry.role] = {
            stance: entry.stance,
            confidence: entry.confidence,
            conceded: entry.stance === "concede",
          };
        }
      }

      set({
        transcript,
        roleState,
        judgeVerdict: verdict,
        status: "completed",
        currentRound: record.rounds_completed,
      });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "回放加载失败";
      set({ error: msg, isReplayMode: false });
    }
  },
}));

function _handleSSEEvent(
  eventType: string,
  data: Record<string, unknown>,
  set: (partial: Partial<DebateStore>) => void,
  get: () => DebateStore,
) {
  const state = get();

  switch (eventType) {
    case "debate_start": {
      // 初始化角色状态
      const roleState: Record<string, RoleState> = {};
      for (const role of DEBATERS) roleState[role] = { ...INITIAL_ROLE_STATE };
      const observerState: Record<string, ObserverState> = {};
      for (const obs of OBSERVERS) observerState[obs] = { speak: false, argument: "" };
      set({ roleState, observerState });
      break;
    }

    case "debate_round_start": {
      const round = data.round as number;
      const is_final = data.is_final as boolean;

      // 推断上一轮观察员沉默
      const prevSpoken = state._observerSpokenThisRound;
      const observerState = { ...state.observerState };
      for (const obs of OBSERVERS) {
        if (!prevSpoken[obs]) {
          observerState[obs] = { ...observerState[obs], speak: false, argument: "" };
        }
      }

      set({
        status: is_final ? "final_round" : "debating",
        currentRound: round,
        observerState,
        _observerSpokenThisRound: {},
        transcript: [
          ...state.transcript,
          { type: "round_divider", round, is_final },
        ],
      });
      break;
    }

    case "debate_entry": {
      const entry = data as unknown as DebateEntry;
      if (DEBATERS.includes(entry.role)) {
        // 更新角色状态
        const roleState = {
          ...state.roleState,
          [entry.role]: {
            stance: entry.stance,
            confidence: entry.confidence,
            conceded: entry.stance === "concede",
          },
        };
        set({
          roleState,
          transcript: [...state.transcript, { type: "entry", data: entry }],
        });
      } else if (OBSERVERS.includes(entry.role)) {
        // 更新观察员状态
        const observerState = {
          ...state.observerState,
          [entry.role]: {
            speak: true,
            argument: entry.argument,
            retail_sentiment_score: entry.retail_sentiment_score ?? undefined,
          },
        };
        set({
          observerState,
          _observerSpokenThisRound: { ...state._observerSpokenThisRound, [entry.role]: true },
        });
      }
      break;
    }

    case "data_fetching": {
      const loadingId = `loading_${Date.now()}`;
      set({ transcript: [...state.transcript, { type: "loading", id: loadingId }] });
      break;
    }

    case "data_ready": {
      // 移除最后一条 loading 条目
      set({
        transcript: state.transcript.filter(
          (item, idx) =>
            !(item.type === "loading" && idx === state.transcript.length - 1)
        ),
      });
      break;
    }

    case "debate_end": {
      const reason = data.reason as string;
      const rounds = data.rounds_completed as number;
      const reasonText = {
        bull_conceded: "多头认输",
        bear_conceded: "空头认输",
        both_conceded: "双方认输",
        max_rounds: "达到最大轮次",
      }[reason] ?? reason;
      set({
        status: "judging",
        transcript: [
          ...state.transcript,
          { type: "system", text: `${reasonText} · 共 ${rounds} 轮` },
        ],
      });
      break;
    }

    case "judge_verdict": {
      set({ judgeVerdict: data as unknown as JudgeVerdict, status: "completed" });
      break;
    }

    case "error": {
      const msg = (data.message as string) ?? "辩论出错";
      set({ error: msg, status: "idle" });
      break;
    }
  }
}
```

- [ ] **Step 2: 提交**

```bash
git add web/stores/useDebateStore.ts
git commit -m "feat: 辩论 zustand store + SSE 状态机"
```
