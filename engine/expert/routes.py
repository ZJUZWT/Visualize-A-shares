"""投资专家 Agent 路由"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from loguru import logger

from expert.agent import ExpertAgent
from expert.schemas import ExpertChatRequest
from expert.tools import ExpertTools

router = APIRouter(prefix="/api/v1/expert", tags=["expert"])

# 全局 Agent 实例
_expert_agent: ExpertAgent | None = None


def _init_db():
    """初始化专家 Agent 数据库和实例"""
    global _expert_agent

    try:
        from data_engine import get_data_engine
        from cluster_engine import get_cluster_engine

        data_engine = get_data_engine()
        cluster_engine = get_cluster_engine()
        llm_engine = None

        try:
            from llm import get_llm_engine
            llm_engine = get_llm_engine()
        except Exception as e:
            logger.warning(f"LLM 引擎加载失败: {e}")

        # 创建工具层
        tools = ExpertTools(
            data_engine=data_engine,
            cluster_engine=cluster_engine,
            llm_engine=llm_engine,
        )

        # 创建知识图谱路径
        kg_path = str(Path("data") / "expert_kg.json")
        Path(kg_path).parent.mkdir(parents=True, exist_ok=True)

        # 创建 Agent 实例
        _expert_agent = ExpertAgent(tools, kg_path=kg_path)
        logger.info("✅ 投资专家 Agent 已初始化")

    except Exception as e:
        logger.error(f"❌ 投资专家 Agent 初始化失败: {e}")
        raise


def get_expert_agent() -> ExpertAgent:
    """获取 Agent 实例"""
    if _expert_agent is None:
        raise RuntimeError("Expert Agent 未初始化")
    return _expert_agent


@router.post("/chat")
async def chat(request: ExpertChatRequest):
    """与专家 Agent 对话（流式）"""
    agent = get_expert_agent()

    async def generate():
        async for chunk in agent.chat(request):
            yield f"data: {chunk}\n\n"

    return generate()


@router.get("/beliefs")
async def get_beliefs():
    """获取当前信念"""
    agent = get_expert_agent()
    beliefs = agent.get_beliefs()
    return {
        "beliefs": [b.model_dump() for b in beliefs]
    }


@router.get("/stances")
async def get_stances():
    """获取当前立场"""
    agent = get_expert_agent()
    stances = agent.get_stances()
    return {
        "stances": [s.model_dump() for s in stances]
    }


@router.get("/knowledge-graph/stats")
async def get_kg_stats():
    """获取知识图谱统计"""
    agent = get_expert_agent()
    kg = agent.get_knowledge_graph()
    stats = kg.stats()
    return stats
