function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function toNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
}

export interface PortfolioSummary {
  id: string;
  mode: string;
  initialCapital: number | null;
  cashBalance: number | null;
  createdAt: string | null;
}

export interface CreatePortfolioDraft {
  id: string;
  mode: string;
  initialCapital: string;
}

export interface CreatePortfolioPayload {
  id: string;
  mode: string;
  initial_capital: number;
  sim_start_date: null;
}

export function normalizePortfolioSummaries(raw: unknown): PortfolioSummary[] {
  if (!Array.isArray(raw)) {
    return [];
  }

  return raw
    .map((item) => {
      if (!isRecord(item) || typeof item.id !== "string") {
        return null;
      }
      return {
        id: item.id,
        mode: typeof item.mode === "string" ? item.mode : "paper",
        initialCapital: toNumber(item.initial_capital),
        cashBalance: toNumber(item.cash_balance),
        createdAt: typeof item.created_at === "string" ? item.created_at : null,
      } satisfies PortfolioSummary;
    })
    .filter((item): item is PortfolioSummary => item !== null);
}

export function pickActivePortfolioId(
  portfolios: PortfolioSummary[],
  currentPortfolioId: string | null,
  preferredPortfolioId: string | null
): string | null {
  if (preferredPortfolioId && portfolios.some((portfolio) => portfolio.id === preferredPortfolioId)) {
    return preferredPortfolioId;
  }
  if (currentPortfolioId && portfolios.some((portfolio) => portfolio.id === currentPortfolioId)) {
    return currentPortfolioId;
  }
  return portfolios[0]?.id ?? null;
}

export function buildCreatePortfolioPayload(
  draft: CreatePortfolioDraft
): { ok: true; value: CreatePortfolioPayload } | { ok: false; error: string } {
  const id = draft.id.trim();
  if (!id) {
    return { ok: false, error: "账户 ID 不能为空。" };
  }

  const initialCapital = Number(draft.initialCapital);
  if (!Number.isFinite(initialCapital) || initialCapital <= 0) {
    return { ok: false, error: "初始资金必须大于 0。" };
  }

  return {
    ok: true,
    value: {
      id,
      mode: draft.mode || "paper",
      initial_capital: initialCapital,
      sim_start_date: null,
    },
  };
}
