"""产业链引擎 API 路由"""

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from loguru import logger

from .schemas import IndustryAnalysisRequest

router = APIRouter(prefix="/api/v1/industry", tags=["industry"])


@router.post("/analyze")
async def analyze_industry(req: IndustryAnalysisRequest):
    """分析产业链认知（SSE 流式推送进度）"""
    from engine.industry import get_industry_engine
    ie = get_industry_engine()

    async def event_stream():
        yield f"event: industry_cognition_start\ndata: {json.dumps({'target': req.target}, ensure_ascii=False)}\n\n"
        try:
            cognition = await ie.analyze(
                target=req.target,
                as_of_date=req.as_of_date,
            )
            if cognition:
                yield f"event: industry_cognition_done\ndata: {json.dumps(cognition.model_dump(), ensure_ascii=False)}\n\n"
            else:
                yield f"event: industry_cognition_done\ndata: {json.dumps({'error': '无法生成行业认知'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"产业链分析失败: {e}")
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/cognition/{target}")
async def get_cognition(target: str, as_of_date: str = ""):
    """获取产业链认知（JSON，缓存优先）"""
    from engine.industry import get_industry_engine
    ie = get_industry_engine()
    cognition = await ie.analyze(target=target, as_of_date=as_of_date)
    if cognition:
        return cognition.model_dump()
    return {"error": f"无法获取 {target} 的行业认知"}


@router.get("/mapping")
async def get_mapping():
    """获取行业→股票映射"""
    from engine.industry import get_industry_engine
    ie = get_industry_engine()
    industries = ie.list_industries()
    return {
        "total_industries": len(industries),
        "industries": [m.model_dump() for m in industries[:50]],
    }


@router.get("/mapping/{industry}")
async def get_industry_stocks(industry: str):
    """获取指定行业的全部股票"""
    from engine.industry import get_industry_engine
    ie = get_industry_engine()
    stocks = ie.get_industry_stocks(industry)
    return {"industry": industry, "stock_count": len(stocks), "stocks": stocks}


@router.get("/capital/{code}")
async def get_capital_structure(code: str, as_of_date: str = ""):
    """获取资金构成分析"""
    from engine.industry import get_industry_engine
    ie = get_industry_engine()
    cs = await ie.get_capital_structure(code, as_of_date)
    return cs.model_dump()


@router.get("/health")
async def health():
    """健康检查"""
    from engine.industry import get_industry_engine
    return get_industry_engine().health_check()


@router.get("/bridge/{target}")
async def bridge_market_assets(target: str, market: str = "", limit: int = 10):
    """获取跨市场桥接资产"""
    from engine.industry import get_industry_engine
    ie = get_industry_engine()
    return ie.bridge_market_assets(target=target, market=market, limit=limit)


# ── 产业链推演端点 ──────────────────────────────────────

from pydantic import BaseModel
from .chain_schemas import ChainExploreRequest, ChainBuildRequest, ChainSimulateRequest


@router.post("/chain/build")
async def chain_build(req: ChainBuildRequest):
    """构建产业链中性网络（SSE 流式推送）

    输入一个"东西"（石油/锂电池/光伏），AI 构建上下游网络，
    所有节点初始 impact=neutral，等待用户交互式施加冲击。
    """
    from . import get_industry_engine
    ie = get_industry_engine()

    if not ie._llm:
        return {"error": "LLM 未配置"}

    from .chain_agent import ChainAgent
    agent = ChainAgent(ie._llm, ie._store)

    async def event_stream():
        try:
            async for event in agent.build(req):
                evt_type = event["event"]
                evt_data = json.dumps(event["data"], ensure_ascii=False, default=str)
                yield f"event: {evt_type}\ndata: {evt_data}\n\n"
        except Exception as e:
            logger.error(f"产业链构建失败: {e}")
            yield f"event: error\ndata: {json.dumps({'message': type(e).__name__}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/chain/simulate")
async def chain_simulate(req: ChainSimulateRequest):
    """冲击传播模拟（SSE 流式推送）

    用户在图上设置某些节点涨/跌，AI 推演冲击波在整个网络中的传播。
    """
    from . import get_industry_engine
    ie = get_industry_engine()

    if not ie._llm:
        return {"error": "LLM 未配置"}

    from .chain_agent import ChainAgent
    agent = ChainAgent(ie._llm, ie._store)

    async def event_stream():
        try:
            async for event in agent.simulate(req):
                evt_type = event["event"]
                evt_data = json.dumps(event["data"], ensure_ascii=False, default=str)
                yield f"event: {evt_type}\ndata: {evt_data}\n\n"
        except Exception as e:
            logger.error(f"冲击模拟失败: {e}")
            yield f"event: error\ndata: {json.dumps({'message': type(e).__name__}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/chain/explore")
async def chain_explore(req: ChainExploreRequest):
    """产业链物理约束推演（SSE 流式推送图谱生长过程）

    事件类型：
    - explore_start: 探索开始
    - depth_start: 某层开始展开
    - nodes_discovered: 发现新节点
    - links_discovered: 发现新边
    - explore_complete: 探索完成
    - error: 错误
    """
    from . import get_industry_engine
    ie = get_industry_engine()

    if not ie._llm:
        return {"error": "LLM 未配置，无法进行产业链推演"}

    from .chain_agent import ChainAgent
    agent = ChainAgent(ie._llm, ie._store)

    async def event_stream():
        try:
            async for event in agent.explore(req):
                evt_type = event["event"]
                evt_data = json.dumps(event["data"], ensure_ascii=False, default=str)
                yield f"event: {evt_type}\ndata: {evt_data}\n\n"
        except Exception as e:
            logger.error(f"产业链推演失败: {e}")
            yield f"event: error\ndata: {json.dumps({'message': type(e).__name__}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


class _ChainExpandRequest(BaseModel):
    event: str
    node_name: str
    existing_nodes: list[str] = []


@router.post("/chain/expand")
async def chain_expand_node(req: _ChainExpandRequest):
    """交互式展开单个节点（用户双击触发）"""
    from . import get_industry_engine
    ie = get_industry_engine()

    if not ie._llm:
        return {"error": "LLM 未配置"}

    from .chain_agent import ChainAgent
    agent = ChainAgent(ie._llm, ie._store)

    expand_req = ChainExploreRequest(
        event=req.event,
        start_node=req.node_name,
        max_depth=1,
    )

    async def event_stream():
        try:
            async for event in agent.explore(expand_req):
                evt_type = event["event"]
                evt_data = json.dumps(event["data"], ensure_ascii=False, default=str)
                yield f"event: {evt_type}\ndata: {evt_data}\n\n"
        except Exception as e:
            logger.error(f"节点展开失败: {e}")
            yield f"event: error\ndata: {json.dumps({'message': type(e).__name__}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── 产业链沙盘 v2 接口 ──────────────────────────────────────


class _ChainParseRequest(BaseModel):
    text: str


@router.post("/chain/parse")
async def chain_parse_input(req: _ChainParseRequest):
    """将任意文本解析为节点列表（不建图，只拆解）"""
    from . import get_industry_engine
    ie = get_industry_engine()

    if not ie._llm:
        # 无 LLM 时回退到关键词匹配
        from .chain_parser import _guess_subject_type_extended
        return {"nodes": [{"name": req.text.strip(), "type": _guess_subject_type_extended(req.text.strip())}]}

    from .chain_parser import ChainInputParser
    parser = ChainInputParser(ie._llm)
    nodes = await parser.parse(req.text)
    return {"nodes": nodes}


class _ChainPlaceNodeRequest(BaseModel):
    node_name: str
    node_type: str = "industry"
    existing_nodes: list[str] = []


@router.post("/chain/place-node")
async def chain_place_node(req: _ChainPlaceNodeRequest):
    """轻量级放置节点：只把节点放到图上 + 发现与已有节点的关系，不自动扩展上下游（SSE）"""
    from . import get_industry_engine
    ie = get_industry_engine()

    if not ie._llm:
        # 无 LLM 时也能放置节点（只是不发现关系）
        from .chain_schemas import ChainNode
        node = ChainNode(
            id=f"n_{req.node_name}",
            name=req.node_name,
            node_type=req.node_type,
            impact="neutral",
            impact_score=0.0,
            depth=0,
            representative_stocks=[],
            constraint=None,
            summary="",
        )
        node_data = json.dumps({"depth": 0, "nodes": [node.model_dump()]}, ensure_ascii=False, default=str)
        complete_data = json.dumps({"node_name": req.node_name}, ensure_ascii=False)

        async def fallback_stream():
            yield f"event: nodes_discovered\ndata: {node_data}\n\n"
            yield f"event: place_node_complete\ndata: {complete_data}\n\n"

        return StreamingResponse(fallback_stream(), media_type="text/event-stream")

    from .chain_agent import ChainAgent
    agent = ChainAgent(ie._llm, ie._store)

    async def event_stream():
        try:
            async for event in agent.place_node(
                node_name=req.node_name,
                node_type=req.node_type,
                existing_nodes=req.existing_nodes,
            ):
                evt_type = event["event"]
                evt_data = json.dumps(event["data"], ensure_ascii=False, default=str)
                yield f"event: {evt_type}\ndata: {evt_data}\n\n"
        except Exception as e:
            logger.error(f"放置节点失败: {e}")
            yield f"event: error\ndata: {json.dumps({'message': type(e).__name__}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


class _ChainAddNodeRequest(BaseModel):
    node_name: str
    node_type: str = "industry"
    existing_nodes: list[str] = []


@router.post("/chain/add-node")
async def chain_add_node(req: _ChainAddNodeRequest):
    """添加一个新节点，LLM 发现它和已有网络的关系（SSE）"""
    from . import get_industry_engine
    ie = get_industry_engine()

    if not ie._llm:
        return {"error": "LLM 未配置"}

    from .chain_agent import ChainAgent
    agent = ChainAgent(ie._llm, ie._store)

    async def event_stream():
        try:
            async for event in agent.add_node(
                node_name=req.node_name,
                node_type=req.node_type,
                existing_nodes=req.existing_nodes,
            ):
                evt_type = event["event"]
                evt_data = json.dumps(event["data"], ensure_ascii=False, default=str)
                yield f"event: {evt_type}\ndata: {evt_data}\n\n"
        except Exception as e:
            logger.error(f"添加节点失败: {e}")
            yield f"event: error\ndata: {json.dumps({'message': type(e).__name__}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


class _ExpandTarget(BaseModel):
    name: str
    direction: str = "both"  # upstream | downstream | both


class _ChainExpandAllRequest(BaseModel):
    leaf_nodes: list[str] = []  # 兼容旧格式（纯名称列表，全部用 both）
    targets: list[_ExpandTarget] = []  # 新格式（带方向）
    existing_nodes: list[str] = []
    existing_links: list[dict] = []  # [{"source": "A", "target": "B", "relation": "upstream"}, ...]
    max_depth: int = 1  # 展开深度


class _ChainRelateBatchRequest(BaseModel):
    new_nodes: list[dict]  # [{"name": "xxx", "node_type": "yyy"}, ...]
    existing_nodes: list[str] = []


@router.post("/chain/relate-batch")
async def chain_relate_batch(req: _ChainRelateBatchRequest):
    """批量发现新节点与已有图谱的跨子网关系（SSE）
    
    一次 LLM 调用代替 N 次 add-node 的串行 relate，
    用于 expandNode 优化：展开后统一发现与旧图的关系。
    """
    from . import get_industry_engine
    ie = get_industry_engine()

    if not ie._llm:
        return {"error": "LLM 未配置"}

    from .chain_agent import ChainAgent
    agent = ChainAgent(ie._llm, ie._store)

    async def event_stream():
        try:
            async for event in agent.relate_batch(
                new_nodes=req.new_nodes,
                existing_nodes=req.existing_nodes,
            ):
                evt_type = event["event"]
                evt_data = json.dumps(event["data"], ensure_ascii=False, default=str)
                yield f"event: {evt_type}\ndata: {evt_data}\n\n"
        except Exception as e:
            logger.error(f"批量relate失败: {e}")
            yield f"event: error\ndata: {json.dumps({'message': type(e).__name__}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


class _ChainReindexRequest(BaseModel):
    nodes: list[dict]  # [{"name": "xxx", "node_type": "yyy"}, ...]
    links: list[dict] = []  # [{"source": "A", "target": "B", "relation": "upstream"}, ...]


@router.post("/chain/reindex-links")
async def chain_reindex_links(req: _ChainReindexRequest):
    """重整关系：审视全图节点，补全缺失的边（SSE）"""
    from . import get_industry_engine
    ie = get_industry_engine()

    if not ie._llm:
        return {"error": "LLM 未配置"}

    from .chain_agent import ChainAgent
    agent = ChainAgent(ie._llm, ie._store)

    async def event_stream():
        try:
            async for event in agent.reindex_links(
                nodes=req.nodes,
                existing_links=req.links,
            ):
                evt_type = event["event"]
                evt_data = json.dumps(event["data"], ensure_ascii=False, default=str)
                yield f"event: {evt_type}\ndata: {evt_data}\n\n"
        except Exception as e:
            logger.error(f"重整关系失败: {e}")
            yield f"event: error\ndata: {json.dumps({'message': type(e).__name__}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/chain/expand-all")
async def chain_expand_all(req: _ChainExpandAllRequest):
    """批量展开所有叶子节点（SSE）"""
    from . import get_industry_engine
    ie = get_industry_engine()

    if not ie._llm:
        return {"error": "LLM 未配置"}

    from .chain_agent import ChainAgent
    agent = ChainAgent(ie._llm, ie._store)

    async def event_stream():
        try:
            # 兼容：旧格式 leaf_nodes → 转为 targets(direction=both)
            targets = req.targets
            if not targets and req.leaf_nodes:
                targets = [_ExpandTarget(name=n, direction="both") for n in req.leaf_nodes]

            async for event in agent.expand_all(
                targets=[(t.name, t.direction) for t in targets],
                existing_nodes=req.existing_nodes,
                existing_links=req.existing_links,
                max_depth=req.max_depth,
            ):
                evt_type = event["event"]
                evt_data = json.dumps(event["data"], ensure_ascii=False, default=str)
                yield f"event: {evt_type}\ndata: {evt_data}\n\n"
        except Exception as e:
            logger.error(f"批量展开失败: {e}")
            yield f"event: error\ndata: {json.dumps({'message': type(e).__name__}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
