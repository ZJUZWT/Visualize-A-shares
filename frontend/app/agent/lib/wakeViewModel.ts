import type {
  CreateWatchSignalPayload,
  InfoDigest,
  WakeDigestMode,
  WakeSummary,
  WatchSignal,
  WatchSignalEvidenceItem,
  WatchSignalFormState,
  WatchSignalStatus,
} from "../types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseMaybeJson(value: unknown): unknown {
  if (typeof value !== "string") {
    return value;
  }
  try {
    return JSON.parse(value) as unknown;
  } catch {
    return value;
  }
}

function normalizeItems(raw: unknown, keys: string[]): unknown[] {
  if (Array.isArray(raw)) {
    return raw;
  }
  if (!isRecord(raw)) {
    return [];
  }
  for (const key of keys) {
    if (Array.isArray(raw[key])) {
      return raw[key] as unknown[];
    }
  }
  return [];
}

function normalizeString(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value.trim() : null;
}

function normalizeStringArray(value: unknown): string[] {
  const parsed = parseMaybeJson(value);
  if (!Array.isArray(parsed)) {
    return [];
  }
  return [...new Set(parsed.map((item) => normalizeString(item)).filter((item): item is string => item !== null))];
}

function normalizeEvidenceItem(value: unknown): WatchSignalEvidenceItem | null {
  if (typeof value === "string") {
    const summary = value.trim();
    return summary ? { title: null, type: null, summary } : null;
  }
  if (!isRecord(value)) {
    return null;
  }
  return {
    title: normalizeString(value.title),
    type: normalizeString(value.type),
    summary:
      normalizeString(value.summary)
      ?? normalizeString(value.content)
      ?? normalizeString(value.title),
  };
}

function normalizeEvidenceList(value: unknown): WatchSignalEvidenceItem[] {
  const parsed = parseMaybeJson(value);
  if (!Array.isArray(parsed)) {
    return [];
  }
  return parsed
    .map((item) => normalizeEvidenceItem(item))
    .filter((item): item is WatchSignalEvidenceItem => item !== null);
}

function normalizeStatus(value: unknown): WatchSignalStatus | null {
  if (typeof value !== "string") {
    return null;
  }
  const normalized = value.trim().toLowerCase();
  if (
    normalized === "watching"
    || normalized === "analyzing"
    || normalized === "triggered"
    || normalized === "failed"
    || normalized === "expired"
    || normalized === "cancelled"
  ) {
    return normalized;
  }
  return null;
}

export function normalizeWatchSignals(raw: unknown): WatchSignal[] {
  const items = normalizeItems(raw, ["items", "signals", "results"]);
  return items.map((item, index) => {
    const data = isRecord(item) ? item : {};
    return {
      id: typeof data.id === "string" ? data.id : `signal-${index}`,
      portfolio_id: normalizeString(data.portfolio_id),
      stock_code: normalizeString(data.stock_code),
      sector: normalizeString(data.sector),
      signal_description: normalizeString(data.signal_description) ?? "",
      check_engine: normalizeString(data.check_engine),
      keywords: normalizeStringArray(data.keywords),
      if_triggered: normalizeString(data.if_triggered),
      cycle_context: normalizeString(data.cycle_context),
      status: normalizeStatus(data.status),
      trigger_evidence: normalizeEvidenceList(data.trigger_evidence),
      source_run_id: normalizeString(data.source_run_id),
      created_at: normalizeString(data.created_at),
      updated_at: normalizeString(data.updated_at),
      triggered_at: normalizeString(data.triggered_at),
    };
  });
}

export function summarizeWatchSignals(signals: WatchSignal[]): WakeSummary {
  let watching = 0;
  let triggered = 0;
  let inactive = 0;

  for (const signal of signals) {
    if (signal.status === "watching" || signal.status === "analyzing") {
      watching += 1;
    } else if (signal.status === "triggered") {
      triggered += 1;
    } else {
      inactive += 1;
    }
  }

  return {
    total: signals.length,
    watching,
    triggered,
    inactive,
  };
}

export function normalizeInfoDigests(raw: unknown): InfoDigest[] {
  const items = normalizeItems(raw, ["items", "digests", "results"]);
  return items.map((item, index) => {
    const data = isRecord(item) ? item : {};
    const structuredSummary = parseMaybeJson(data.structured_summary);
    const rawSummary = parseMaybeJson(data.raw_summary);
    const structured = isRecord(structuredSummary) ? structuredSummary : {};
    const rawNormalized = isRecord(rawSummary) ? rawSummary : null;

    return {
      id: typeof data.id === "string" ? data.id : `digest-${index}`,
      portfolio_id: normalizeString(data.portfolio_id),
      run_id: normalizeString(data.run_id),
      stock_code: normalizeString(data.stock_code),
      digest_type: normalizeString(data.digest_type),
      summary: normalizeString(structured.summary) ?? normalizeString(data.summary),
      key_evidence: normalizeStringArray(structured.key_evidence ?? data.key_evidence),
      risk_flags: normalizeStringArray(structured.risk_flags ?? data.risk_flags),
      strategy_relevance: normalizeString(data.strategy_relevance),
      impact_assessment: normalizeString(data.impact_assessment),
      missing_sources: normalizeStringArray(data.missing_sources),
      structured_summary: isRecord(structuredSummary) ? structuredSummary : null,
      raw_summary: rawNormalized,
      created_at: normalizeString(data.created_at),
    };
  });
}

export function filterInfoDigestsForRun(
  digests: InfoDigest[],
  runId: string | null,
  mode: WakeDigestMode
): InfoDigest[] {
  if (mode === "recent") {
    return digests;
  }
  if (!runId) {
    return digests;
  }
  const selectedRunDigests = digests.filter((digest) => digest.run_id === runId);
  return selectedRunDigests.length > 0 ? selectedRunDigests : digests;
}

export function buildWatchSignalPayload(
  portfolioId: string | null,
  form: WatchSignalFormState
): CreateWatchSignalPayload | null {
  if (!portfolioId) {
    return null;
  }

  const stockCode = form.stock_code.trim().toUpperCase();
  const signalDescription = form.signal_description.trim();
  if (!stockCode || !signalDescription) {
    return null;
  }

  const keywords = [...new Set(
    form.keywords
      .split(",")
      .map((item) => item.trim())
      .filter((item) => item.length > 0)
  )];

  const payload: CreateWatchSignalPayload = {
    portfolio_id: portfolioId,
    stock_code: stockCode,
    signal_description: signalDescription,
    check_engine: "info",
    keywords,
    status: "watching",
  };

  const sector = form.sector.trim();
  const ifTriggered = form.if_triggered.trim();
  const cycleContext = form.cycle_context.trim();

  if (sector) {
    payload.sector = sector;
  }
  if (ifTriggered) {
    payload.if_triggered = ifTriggered;
  }
  if (cycleContext) {
    payload.cycle_context = cycleContext;
  }

  return payload;
}
