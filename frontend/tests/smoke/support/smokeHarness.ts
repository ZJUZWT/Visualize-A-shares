import type { ConsoleMessage, Page } from "@playwright/test";
import { expect } from "@playwright/test";

import {
  formatRuntimeIssues,
  isBadHttpStatus,
  shouldIgnoreConsoleErrorText,
  shouldIgnoreFailedRequestUrl,
  type RuntimeIssue,
} from "./runtimeIssues";

const EXPERT_PROFILES = [
  {
    type: "data",
    name: "数据专家",
    icon: "📊",
    color: "#60A5FA",
    description: "行情查询、股票搜索、聚类分析、全市场概览",
    suggestions: [],
  },
  {
    type: "quant",
    name: "量化专家",
    icon: "🔬",
    color: "#A78BFA",
    description: "技术指标、因子评分、IC 回测、条件选股",
    suggestions: [],
  },
  {
    type: "info",
    name: "资讯专家",
    icon: "📰",
    color: "#F59E0B",
    description: "新闻情感、公告解读、事件影响评估",
    suggestions: [],
  },
  {
    type: "industry",
    name: "产业链专家",
    icon: "🏭",
    color: "#10B981",
    description: "行业认知、产业链映射、资金构成、周期分析",
    suggestions: [],
  },
  {
    type: "rag",
    name: "投资顾问",
    icon: "🧠",
    color: "#EC4899",
    description: "自由对话、知识图谱、信念系统、综合分析",
    suggestions: [],
  },
  {
    type: "short_term",
    name: "短线专家",
    icon: "⚡",
    color: "#F97316",
    description: "短线交易、量价节奏、板块轮动、1-5日操作策略",
    suggestions: [],
  },
];

const DEMO_PORTFOLIO = {
  id: "demo",
  mode: "paper",
  initial_capital: 1_000_000,
  cash_balance: 1_000_000,
  created_at: "2026-03-24T09:00:00",
};

interface AgentPortfolioMock {
  id: string;
  mode?: string;
  initial_capital?: number;
  cash_balance?: number;
  created_at?: string;
}

interface ApiMockOptions {
  agentPortfolios?: AgentPortfolioMock[];
}

const SECTOR_BOARDS = {
  boards: [
    {
      board_code: "BK001",
      board_name: "白酒",
      board_type: "industry",
      close: 100,
      pct_chg: 1.2,
      volume: 1_000,
      amount: 100_000,
      turnover_rate: 2.1,
      total_mv: 1_000,
      rise_count: 10,
      fall_count: 2,
      leading_stock: "贵州茅台",
      leading_pct_chg: 2.3,
      main_force_net_inflow: 10,
      main_force_net_ratio: 1.5,
      prediction_score: 0.7,
      prediction_signal: "bullish",
    },
  ],
};

function toJsonResponse(body: unknown) {
  return {
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  };
}

function normalizePortfolioMock(
  portfolio: AgentPortfolioMock,
  index: number
): Required<AgentPortfolioMock> {
  const capital = portfolio.initial_capital ?? 1_000_000;
  return {
    id: portfolio.id,
    mode: portfolio.mode ?? "paper",
    initial_capital: capital,
    cash_balance: portfolio.cash_balance ?? capital,
    created_at: portfolio.created_at ?? `2026-03-24T09:00:0${index}`,
  };
}

function buildEmptyLedger(portfolioId: string, capital: number) {
  return {
    portfolio_id: portfolioId,
    account: {
      cash_balance: capital,
      total_asset: capital,
      total_pnl: 0,
      total_pnl_pct: 0,
      position_count: 0,
      pending_plan_count: 0,
      trade_count: 0,
    },
    positions: [],
    pending_plans: [],
    recent_trades: [],
  };
}

function buildEquityTimeline(portfolioId: string, capital: number) {
  return {
    portfolio_id: portfolioId,
    start_date: "2026-03-20",
    end_date: "2026-03-24",
    mark_to_market: [
      {
        date: "2026-03-24",
        equity: capital,
        cash_balance: capital,
        position_value: 0,
        position_cost_basis_open: 0,
        realized_pnl: 0,
        unrealized_pnl: 0,
      },
    ],
    realized_only: [
      {
        date: "2026-03-24",
        equity: capital,
        cash_balance: capital,
        position_value: 0,
        position_cost_basis_open: 0,
        realized_pnl: 0,
        unrealized_pnl: 0,
      },
    ],
  };
}

function buildReplaySnapshot(portfolioId: string, capital: number) {
  return {
    portfolio_id: portfolioId,
    date: "2026-03-24",
    account: {
      cash_balance: capital,
      position_value_mark_to_market: 0,
      position_cost_basis_open: 0,
      total_asset_mark_to_market: capital,
      total_asset_realized_only: capital,
      realized_pnl: 0,
      unrealized_pnl: 0,
    },
    positions: [],
    trades: [],
    plans: [],
    brain_runs: [],
    reviews: [],
    reflections: [],
    what_ai_knew: {
      run_ids: [],
      trade_theses: [],
      plan_reasoning: [],
      trade_reasons: [],
    },
    what_happened: {
      review_statuses: [],
    },
  };
}

function buildReplayLearning(portfolioId: string, capital: number) {
  return {
    portfolio_id: portfolioId,
    date: "2026-03-24",
    what_ai_knew: {
      run_ids: [],
      trade_theses: [],
      plan_reasoning: [],
      trade_reasons: [],
    },
    what_happened: {
      review_statuses: [],
      next_day_move_pct: 0,
      total_asset_mark_to_market_close: capital,
      total_asset_realized_only_close: capital,
    },
    counterfactual: {
      would_change: false,
      action_bias: null,
      rationale: null,
    },
    lesson_summary: "smoke test mock",
  };
}

function isIgnorableConsoleMessage(message: ConsoleMessage): boolean {
  return shouldIgnoreConsoleErrorText(message.text());
}

export function attachPageErrorCollectors(page: Page): RuntimeIssue[] {
  const runtimeErrors: RuntimeIssue[] = [];

  page.on("console", (message) => {
    if (message.type() !== "error" || isIgnorableConsoleMessage(message)) {
      return;
    }
    runtimeErrors.push({
      source: "console",
      message: message.text(),
    });
  });

  page.on("pageerror", (error) => {
    runtimeErrors.push({
      source: "pageerror",
      message: error.message,
    });
  });

  page.on("requestfailed", (request) => {
    if (shouldIgnoreFailedRequestUrl(request.url())) {
      return;
    }
    runtimeErrors.push({
      source: "requestfailed",
      message: `${request.method()} ${request.url()} :: ${request.failure()?.errorText || "request failed"}`,
    });
  });

  page.on("response", (response) => {
    if (!isBadHttpStatus(response.status()) || shouldIgnoreFailedRequestUrl(response.url())) {
      return;
    }
    runtimeErrors.push({
      source: "response",
      message: `${response.status()} ${response.request().method()} ${response.url()}`,
    });
  });

  return runtimeErrors;
}

export async function installWebSocketMock(page: Page): Promise<void> {
  await page.addInitScript(() => {
    class MockWebSocket {
      static readonly CONNECTING = 0;
      static readonly OPEN = 1;
      static readonly CLOSING = 2;
      static readonly CLOSED = 3;

      readonly url: string;
      readyState = MockWebSocket.CONNECTING;
      onopen: ((event: Event) => void) | null = null;
      onmessage: ((event: MessageEvent) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      onclose: ((event: CloseEvent) => void) | null = null;

      constructor(url: string) {
        this.url = url;
        window.setTimeout(() => {
          this.readyState = MockWebSocket.OPEN;
          this.onopen?.(new Event("open"));
        }, 0);
      }

      addEventListener(type: string, listener: EventListenerOrEventListenerObject) {
        const callback = typeof listener === "function"
          ? listener
          : (event: Event) => listener.handleEvent(event);
        if (type === "open") {
          this.onopen = callback as (event: Event) => void;
        } else if (type === "message") {
          this.onmessage = callback as (event: MessageEvent) => void;
        } else if (type === "error") {
          this.onerror = callback as (event: Event) => void;
        } else if (type === "close") {
          this.onclose = callback as (event: CloseEvent) => void;
        }
      }

      removeEventListener() {}

      send() {}

      close() {
        this.readyState = MockWebSocket.CLOSED;
        this.onclose?.(new CloseEvent("close"));
      }
    }

    Object.defineProperty(window, "WebSocket", {
      configurable: true,
      writable: true,
      value: MockWebSocket,
    });
  });
}

export async function installApiMocks(page: Page, options: ApiMockOptions = {}): Promise<void> {
  let agentPortfolios = (options.agentPortfolios ?? [DEMO_PORTFOLIO]).map(normalizePortfolioMock);

  const getPortfolioById = (portfolioId: string) =>
    agentPortfolios.find((portfolio) => portfolio.id === portfolioId) ?? null;

  const getActivePortfolio = () => agentPortfolios[0] ?? normalizePortfolioMock(DEMO_PORTFOLIO, 0);

  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const pathname = url.pathname;
    const method = route.request().method().toUpperCase();

    const activePortfolio = getActivePortfolio();
    const activePortfolioId = url.searchParams.get("portfolio_id") ?? activePortfolio.id;
    const activeCapital = getPortfolioById(activePortfolioId)?.initial_capital ?? activePortfolio.initial_capital;

    if (method === "POST" && pathname === "/api/v1/agent/portfolio") {
      const payload = JSON.parse(route.request().postData() ?? "{}") as AgentPortfolioMock;
      const createdPortfolio = normalizePortfolioMock(payload, agentPortfolios.length);
      agentPortfolios = [...agentPortfolios, createdPortfolio];
      await route.fulfill(toJsonResponse(createdPortfolio));
      return;
    }

    if (method !== "GET") {
      await route.fulfill(toJsonResponse({ ok: true }));
      return;
    }

    switch (pathname) {
      case "/api/v1/expert/profiles":
        await route.fulfill(toJsonResponse(EXPERT_PROFILES));
        return;
      case "/api/v1/expert/sessions":
      case "/api/v1/expert/tasks":
      case "/api/v1/debate/history":
      case "/api/v1/agent/brain/runs":
      case "/api/v1/agent/plans":
      case "/api/v1/agent/reviews":
      case "/api/v1/agent/reviews/weekly":
      case "/api/v1/agent/memories":
      case "/api/v1/agent/reflections":
      case "/api/v1/agent/strategy/history":
      case "/api/v1/agent/watch-signals":
      case "/api/v1/agent/info-digests":
      case "/api/v1/agent/chat/sessions":
      case "/api/v1/agent/strategy-actions":
      case "/api/v1/agent/strategy-memos":
      case "/api/v1/agent/watchlist":
        await route.fulfill(toJsonResponse([]));
        return;
      case "/api/v1/agent/portfolio":
        await route.fulfill(toJsonResponse(agentPortfolios));
        return;
      case "/api/v1/agent/state":
        await route.fulfill(toJsonResponse({ portfolio_id: activePortfolioId }));
        return;
      case "/api/v1/agent/ledger/overview":
        await route.fulfill(toJsonResponse(buildEmptyLedger(activePortfolioId, activeCapital)));
        return;
      case "/api/v1/agent/timeline/equity":
        await route.fulfill(toJsonResponse(buildEquityTimeline(activePortfolioId, activeCapital)));
        return;
      case "/api/v1/agent/timeline/replay":
        await route.fulfill(toJsonResponse(buildReplaySnapshot(activePortfolioId, activeCapital)));
        return;
      case "/api/v1/agent/timeline/replay-learning":
        await route.fulfill(toJsonResponse(buildReplayLearning(activePortfolioId, activeCapital)));
        return;
      case "/api/v1/agent/reviews/stats":
        await route.fulfill(toJsonResponse({
          total_reviews: 0,
          win_rate: 0,
          avg_pnl_pct: 0,
          avg_holding_days: 0,
          by_review_type: {},
        }));
        return;
      case "/api/v1/sector/boards":
        await route.fulfill(toJsonResponse(SECTOR_BOARDS));
        return;
      default:
        if (pathname.startsWith("/api/v1/agent/portfolio/")) {
          const portfolioId = pathname.split("/")[5] ?? activePortfolio.id;
          if (pathname.endsWith("/trades")) {
            await route.fulfill(toJsonResponse([]));
            return;
          }
          const portfolio = getPortfolioById(portfolioId) ?? getActivePortfolio();
          await route.fulfill(toJsonResponse({
            ...portfolio,
            total_asset: portfolio.initial_capital,
            total_pnl: 0,
            total_pnl_pct: 0,
          }));
          return;
        }

        if (pathname.startsWith("/api/v1/agent/chat/sessions/")) {
          await route.fulfill(toJsonResponse([]));
          return;
        }

        await route.fulfill(toJsonResponse({}));
    }
  });
}

export function assertNoRuntimeErrors(
  routePath: string,
  runtimeErrors: RuntimeIssue[]
): void {
  const messages = formatRuntimeIssues(routePath, runtimeErrors);
  expect(messages, `runtime errors found on ${routePath}`).toEqual([]);
}
