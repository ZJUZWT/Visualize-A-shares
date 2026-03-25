interface CanvasLike {
  getContext?: (
    contextId: "webgl2" | "webgl" | "experimental-webgl",
    options?: Record<string, unknown>,
  ) => unknown;
}

interface DocumentLike {
  createElement: (tagName: string) => CanvasLike;
}

const WEBGL_CONTEXT_IDS = ["webgl2", "webgl", "experimental-webgl"] as const;

export function canUseWebGL(documentLike: DocumentLike | null | undefined): boolean {
  if (!documentLike) {
    return false;
  }

  const canvas = documentLike.createElement("canvas");
  if (!canvas || typeof canvas.getContext !== "function") {
    return false;
  }

  for (const contextId of WEBGL_CONTEXT_IDS) {
    try {
      if (canvas.getContext(contextId, { failIfMajorPerformanceCaveat: true })) {
        return true;
      }
    } catch {
      continue;
    }
  }

  return false;
}
