"""最终集成测试 — 修复后 chain/build 端到端"""
import asyncio, json, sys, os, time
os.chdir(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, ".")

async def heartbeat():
    while True:
        await asyncio.sleep(5)
        print("  ...", flush=True)

async def main():
    from llm.config import LLMConfig
    from llm.providers import LLMProviderFactory
    from engine.industry.chain_agent import ChainAgent, _guess_subject_type
    from engine.industry.chain_schemas import ChainBuildRequest

    cfg = LLMConfig.from_env()
    print(f"max_tokens={cfg.max_tokens}", flush=True)

    provider = LLMProviderFactory.create(cfg)
    agent = ChainAgent(provider)
    req = ChainBuildRequest(subject="中泰化学", max_depth=1)

    print(f"开始构建: {req.subject} (max_depth={req.max_depth})", flush=True)
    hb = asyncio.create_task(heartbeat())

    t0 = time.time()
    node_names = []
    link_count = 0
    errors = []

    async for event in agent.build(req):
        evt_type = event["event"]
        data = event["data"]
        elapsed = time.time() - t0

        if evt_type == "nodes_discovered":
            nodes = data.get("nodes", [])
            names = [nd["name"] for nd in nodes]
            node_names.extend(names)
            print(f"  [{elapsed:5.0f}s] +{len(nodes)} nodes: {names}", flush=True)
        elif evt_type == "links_discovered":
            n = len(data.get("links", []))
            link_count += n
            edges = [(l["source"], l["target"]) for l in data["links"][:3]]
            print(f"  [{elapsed:5.0f}s] +{n} links, 样例: {edges}", flush=True)
        elif evt_type == "error":
            errors.append(data)
            print(f"  [{elapsed:5.0f}s] ❌ {data}", flush=True)
        else:
            print(f"  [{elapsed:5.0f}s] {evt_type}", flush=True)

    hb.cancel()
    total = time.time() - t0

    print(f"\n{'='*60}", flush=True)
    print(f"耗时: {total:.0f}s", flush=True)
    print(f"节点: {len(node_names)} → {node_names}", flush=True)
    print(f"边: {link_count}", flush=True)

    if errors:
        print(f"\n❌ 有 {len(errors)} 个错误", flush=True)
    elif len(node_names) >= 3:
        print(f"\n✅ 构建成功! 中泰化学产业链包含 {len(node_names)} 个节点", flush=True)
    elif len(node_names) > 1:
        print(f"\n⚠️ 部分成功 — 节点较少（可能 JSON 被截断）", flush=True)
    else:
        print(f"\n❌ 失败 — 仅有根节点", flush=True)

asyncio.run(main())
