import type { WatchlistItem } from "../types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function normalizeWatchlist(raw: unknown): WatchlistItem[] {
  if (!Array.isArray(raw)) {
    return [];
  }

  return raw.flatMap((item) => {
    if (!isRecord(item)) {
      return [];
    }

    const id = typeof item.id === "string" ? item.id : null;
    const stockCode = typeof item.stock_code === "string" ? item.stock_code : null;
    const stockName = typeof item.stock_name === "string" ? item.stock_name : null;

    if (!id || !stockCode || !stockName) {
      return [];
    }

    return [{
      id,
      stock_code: stockCode,
      stock_name: stockName,
      reason: typeof item.reason === "string" ? item.reason : null,
      added_by: typeof item.added_by === "string" ? item.added_by : "unknown",
      created_at: typeof item.created_at === "string" ? item.created_at : "",
    }];
  });
}
