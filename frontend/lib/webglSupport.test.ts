import test from "node:test";
import assert from "node:assert/strict";

import { canUseWebGL } from "./webglSupport.ts";

test("canUseWebGL returns false when document is unavailable", () => {
  assert.equal(canUseWebGL(null), false);
});

test("canUseWebGL returns true when a supported context can be created", () => {
  const calls: string[] = [];
  const documentLike = {
    createElement() {
      return {
        getContext(contextId: "webgl2" | "webgl" | "experimental-webgl") {
          calls.push(contextId);
          return contextId === "webgl" ? { ok: true } : null;
        },
      };
    },
  };

  assert.equal(canUseWebGL(documentLike), true);
  assert.deepEqual(calls, ["webgl2", "webgl"]);
});

test("canUseWebGL returns false when all context attempts fail", () => {
  const documentLike = {
    createElement() {
      return {
        getContext() {
          throw new Error("context unavailable");
        },
      };
    },
  };

  assert.equal(canUseWebGL(documentLike), false);
});
