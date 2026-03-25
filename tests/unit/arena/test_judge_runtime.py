import asyncio
from types import SimpleNamespace


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_round_eval_uses_fast_tier_llm():
    from engine.arena.judge import JudgeRAG
    from engine.arena.schemas import Blackboard, DebateEntry

    class FakeFastLLM:
        def __init__(self):
            self.calls = 0

        async def chat_stream(self, messages):
            self.calls += 1
            yield """{
              "bull": {"self_confidence": 0.7, "inner_confidence": 0.6, "judge_confidence": 0.65},
              "bear": {"self_confidence": 0.5, "inner_confidence": 0.4, "judge_confidence": 0.45},
              "bull_reasoning": "多头证据更完整",
              "bear_reasoning": "空头催化不足",
              "data_utilization": {"used": true}
            }"""

    class FakeQualityLLM:
        async def chat_stream(self, messages):
            raise AssertionError("round_eval should not use quality llm")

    fast_llm = FakeFastLLM()
    quality_llm = FakeQualityLLM()
    expert = SimpleNamespace(
        _llm=quality_llm,
        _get_fast_llm=lambda: fast_llm,
        _graph=SimpleNamespace(recall=lambda query: []),
    )

    judge = JudgeRAG(expert)
    blackboard = Blackboard(
        target="贵州茅台",
        debate_id="600519_20260324120000",
        transcript=[
            DebateEntry(role="bull_expert", round=1, argument="需求回暖", confidence=0.7),
            DebateEntry(role="bear_expert", round=1, argument="估值偏高", confidence=0.5),
        ],
        round=1,
    )

    result = run(judge.round_eval(1, blackboard))

    assert result.bull.judge_confidence == 0.65
    assert fast_llm.calls == 1
