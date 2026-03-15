"""
StockTerrain Engine — FastAPI 应用入口

启动方式:
    cd engine
    uvicorn main:app --reload --port 8000
    
或:
    python main.py
"""

import sys
from pathlib import Path

# 将 engine 目录加入 Python 路径
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from config import settings
from data_engine.routes import router as data_router
from cluster_engine.routes import router as cluster_router
from api.routes.chat import router as chat_router
from quant_engine.routes import router as quant_router
from api.routes.analysis import router as analysis_router
from api.routes.debate import router as debate_router
from info_engine.routes import router as info_router
from expert.routes import router as expert_router, _init_db as expert_init_db

# ─── 配置日志 ──────────────────────────────────────────
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | <cyan>{message}</cyan>",
    level="INFO",
)
logger.add(
    "logs/engine_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    retention="30 days",
    level="DEBUG",
)

# ─── 创建 FastAPI 应用 ─────────────────────────────────
app = FastAPI(
    title="StockTerrain Engine",
    description="A股多维聚类 3D 地形可视化平台 — 数据与算法引擎",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── CORS 中间件 ──────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.server.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── 注册路由 ─────────────────────────────────────────
app.include_router(data_router)
app.include_router(cluster_router)
app.include_router(chat_router)
app.include_router(quant_router)
app.include_router(analysis_router)
app.include_router(debate_router)
app.include_router(info_router)
app.include_router(expert_router)


# ─── 启动/关闭事件 ────────────────────────────────────
@app.on_event("startup")
async def startup():
    from llm.config import llm_settings
    logger.info("=" * 60)
    logger.info("🏔️  StockTerrain Engine 启动")
    logger.info(f"   数据源: AKShare(主力) + BaoStock(备选)")
    logger.info(f"   算法: HDBSCAN + UMAP + RBF")
    logger.info(f"   预测: v2.0 (MAD去极值 + 正交化 + ICIR自适应权重)")
    logger.info(f"   量化引擎: 已加载 (13因子 + 技术指标)")
    logger.info(f"   信息引擎: 已加载 (新闻+公告+情感分析)")
    logger.info(f"   LLM: {'已配置 (' + llm_settings.provider + '/' + llm_settings.model + ')' if llm_settings.api_key else '未配置 (可在设置中启用)'}")
    logger.info(f"   端口: {settings.server.port}")
    logger.info(f"   API 文档: http://localhost:{settings.server.port}/docs")
    logger.info("=" * 60)

    # 自动尝试 ICIR 权重校准（通过 QuantEngine）
    if settings.quant.auto_inject_on_startup:
        try:
            from quant_engine import get_quant_engine
            qe = get_quant_engine()
            qe.try_auto_inject_icir_weights()
            # 同步到 ClusterEngine 的 pipeline（单独 try 避免掩盖 ClusterEngine 初始化错误）
            if qe.predictor._icir_weights is not None:
                try:
                    from cluster_engine import get_cluster_engine
                    get_cluster_engine().pipeline.predictor_v2.set_icir_weights(
                        qe.predictor._icir_weights
                    )
                except Exception as e:
                    logger.warning(f"⚠️ ICIR 权重同步到 ClusterEngine 失败: {e}")
        except Exception as e:
            logger.warning(f"⚠️ ICIR 自动校准跳过: {e}")

    # 初始化投资专家 Agent
    try:
        await expert_init_db()
    except Exception as e:
        logger.warning(f"⚠️ 投资专家 Agent 初始化失败: {e}")


@app.on_event("shutdown")
async def shutdown():
    logger.info("🏔️  StockTerrain Engine 关闭")


# ─── 根路由 ────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "name": "StockTerrain Engine",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
        "endpoints": {
            "health": "/api/v1/health",
            "compute": "POST /api/v1/terrain/compute",
            "refresh": "GET /api/v1/terrain/refresh",
            "search": "GET /api/v1/stocks/search?q=xxx",
            "factor_backtest": "POST /api/v1/factor/backtest",
            "factor_weights": "GET /api/v1/factor/weights",
            "websocket": "WS /api/v1/ws/terrain",
            "chat": "POST /api/v1/chat (SSE 流式)",
            "chat_sync": "POST /api/v1/chat/sync",
            "chat_config": "GET/POST /api/v1/chat/config",
            "data_health": "GET /api/v1/data/health",
            "data_snapshot": "GET /api/v1/data/snapshot",
            "data_daily": "GET /api/v1/data/daily/{code}",
            "data_profiles": "GET /api/v1/data/profiles",
            "quant_health": "GET /api/v1/quant/health",
            "quant_factor_weights": "GET /api/v1/quant/factor/weights",
            "quant_factor_defs": "GET /api/v1/quant/factor/defs",
            "quant_backtest": "POST /api/v1/quant/factor/backtest",
            "quant_indicators": "GET /api/v1/quant/indicators/{code}",
            "analysis": "POST /api/v1/analysis (SSE 流式)",
            "info_health": "GET /api/v1/info/health",
            "info_news": "GET /api/v1/info/news/{code}",
            "info_announcements": "GET /api/v1/info/announcements/{code}",
            "info_assess": "POST /api/v1/info/assess",
        },
    }


# ─── 直接运行 ─────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.reload,
        log_level="info",
    )
