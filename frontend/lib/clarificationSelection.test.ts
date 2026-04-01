import test from "node:test";
import assert from "node:assert/strict";

import {
  buildClarificationSelections,
  shouldAutoAdvanceClarification,
  toggleClarificationOption,
  toggleClarificationSubChoice,
} from "./clarificationSelection.ts";
import type { ClarificationOption, ClarificationRequestData } from "../types/expert.ts";

const baseOption: ClarificationOption = {
  id: "valuation",
  label: "A",
  title: "先看估值",
  description: "先看估值和安全边际。",
  focus: "估值、安全边际",
};

test("single select does not auto submit before confirm", () => {
  const draft = toggleClarificationOption(new Map(), baseOption, false);

  assert.equal(draft.size, 1);
  assert.deepEqual(buildClarificationSelections(draft), [
    {
      option_id: "valuation",
      label: "A",
      title: "先看估值",
      focus: "估值、安全边际",
      skip: false,
    },
  ]);
});

test("clicking the same sub choice toggles it off", () => {
  const option: ClarificationOption = {
    ...baseOption,
    id: "style",
    sub_choices: [
      { id: "short", label: "①", text: "短线" },
      { id: "long", label: "②", text: "长线" },
    ],
  };

  const selected = toggleClarificationSubChoice(new Map(), option, "short", "短线", false);
  assert.equal(selected.size, 1);

  const toggledOff = toggleClarificationSubChoice(selected, option, "short", "短线", false);
  assert.equal(toggledOff.size, 0);
});

test("empty options do not auto advance while clarification is still required", () => {
  const pendingClarify: ClarificationRequestData = {
    should_clarify: true,
    question_summary: "你更想先确认哪个方向？",
    options: [],
    reasoning: "还需要用户手动确认",
    skip_option: {
      id: "skip",
      label: "S",
      title: "跳过，直接分析",
      description: "直接进入完整分析。",
      focus: "完整分析",
    },
    needs_more: true,
    round: 2,
    max_rounds: 3,
    multi_select: false,
  };

  assert.equal(shouldAutoAdvanceClarification(pendingClarify), false);
  assert.equal(
    shouldAutoAdvanceClarification({ ...pendingClarify, should_clarify: false }),
    true,
  );
});
