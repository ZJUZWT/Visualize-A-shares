export type SseInspectionResult =
  | { ok: true }
  | { ok: false; error: string };

function extractErrorMessage(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") return null;
  const record = payload as Record<string, unknown>;
  for (const key of ["error", "detail", "message"]) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return null;
}

export async function inspectSseResponse(res: Response): Promise<SseInspectionResult> {
  const contentType = (res.headers.get("content-type") || "").toLowerCase();

  if (contentType.includes("text/event-stream")) {
    return { ok: true };
  }

  if (!res.ok) {
    return { ok: false, error: `HTTP ${res.status}` };
  }

  if (contentType.includes("application/json")) {
    try {
      const payload = await res.clone().json();
      const message = extractErrorMessage(payload);
      if (message) {
        return { ok: false, error: message };
      }
    } catch {
      // fall through to generic error below
    }
  }

  return { ok: false, error: `HTTP ${res.status}` };
}
