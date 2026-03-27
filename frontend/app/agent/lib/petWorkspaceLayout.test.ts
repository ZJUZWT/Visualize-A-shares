import test from "node:test";
import assert from "node:assert/strict";

import { buildPetWorkspaceLayout } from "./petWorkspaceLayout.ts";

test("buildPetWorkspaceLayout keeps strategy under stage and chat on the right rail", () => {
  const layout = buildPetWorkspaceLayout();

  assert.deepEqual(layout.leftStack, ["stage", "strategy"]);
  assert.deepEqual(layout.rightStack, ["chat"]);
  assert.match(layout.rootClassName, /xl:grid-cols/);
  assert.match(layout.leftColumnClassName, /flex-col/);
  assert.match(layout.rightColumnClassName, /min-h-\[780px\]/);
});
