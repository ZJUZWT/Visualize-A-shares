"""
StockScape Engine — FastAPI 应用入口

启动方式:
    cd backend
    uvicorn main:app --reload --port 8000
    
或:
    python main.py
"""

import sys
from pathlib import Path
from contextlib import asynccontextmanager

# 将 backend 目录加入 Python 路径
sys.path.insert(0, str(Path(__file__).resolve().parent))

import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel

from config import settings
from engine.data.routes import router as data_router
from engine.cluster.routes import router as cluster_router
from api.routes.chat import router as chat_router
from engine.quant.routes import router as quant_router
from api.routes.analysis import router as analysis_router
from api.routes.debate import router as debate_router
from engine.info.routes import router as info_router
from engine.expert.routes import router as expert_router, _init_db as expert_init_db
from engine.industry.routes import router as industry_router
from engine.sector.routes import router as sector_router
from engine.agent.routes import create_agent_router

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

async def _startup() -> None:
    from llm.config import llm_settings

    logger.info("=" * 60)
    logger.info("🌄  StockScape Engine 启动")
    logger.info(f"   数据源: AKShare(主力) + BaoStock(备选)")
    logger.info(f"   算法: HDBSCAN + UMAP + RBF")
    logger.info(f"   预测: v2.0 (MAD去极值 + 正交化 + ICIR自适应权重)")
    logger.info(f"   量化引擎: 已加载 (13因子 + 技术指标)")
    logger.info(f"   信息引擎: 已加载 (新闻+公告+情感分析)")
    logger.info(f"   产业链引擎: 已加载 (行业认知+映射+资金构成)")
    logger.info(f"   LLM: {'已配置 (' + llm_settings.provider + '/' + llm_settings.model + ')' if llm_settings.api_key else '未配置 (可在设置中启用)'}")
    logger.info(f"   端口: {settings.server.port}")
    logger.info(f"   API 文档: http://localhost:{settings.server.port}/docs")
    logger.info("=" * 60)

    # 自动尝试 ICIR 权重校准（通过 QuantEngine）
    if settings.quant.auto_inject_on_startup:
        try:
            from engine.quant import get_quant_engine
            qe = get_quant_engine()
            qe.try_auto_inject_icir_weights()
            # 同步到 ClusterEngine 的 pipeline（单独 try 避免掩盖 ClusterEngine 初始化错误）
            if qe.predictor._icir_weights is not None:
                try:
                    from engine.cluster import get_cluster_engine
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

    # 初始化 Main Agent 数据库
    try:
        from engine.agent.db import AgentDB
        AgentDB.init_instance()
        logger.info("   Main Agent DB: 已初始化")
    except Exception as e:
        logger.warning(f"⚠️ Main Agent DB 初始化失败: {e}")

    # 初始化 users 表
    try:
        from auth import ensure_default_admin, ensure_users_table
        ensure_users_table()
        ensure_default_admin()
    except Exception as e:
        logger.warning(f"⚠️ Users 表初始化失败: {e}")

    # 启动 Agent Brain 调度器
    try:
        from engine.agent.scheduler import AgentScheduler
        agent_scheduler = AgentScheduler.get_instance()
        agent_scheduler.start()
        logger.info("   Agent Brain 调度器: 已启动")
    except Exception as e:
        logger.warning(f"⚠️ Agent Brain 调度器启动失败: {e}")

    # 异步探测 Responses API 支持（不阻塞启动）
    if llm_settings.api_key and llm_settings.provider == "openai_compatible":
        import asyncio
        async def _probe():
            try:
                from llm.providers import LLMProviderFactory
                provider = LLMProviderFactory.create(llm_settings)
                supported = await provider.probe_responses_api()
                logger.info(f"   Responses API: {'✅ 可用' if supported else '⬇️ 不可用，使用 Chat Completions'}")
            except Exception as e:
                logger.debug(f"Responses API 探测异常: {e}")
        asyncio.create_task(_probe())


async def _shutdown() -> None:
    # 关闭定时任务调度器
    try:
        from engine.expert.routes import get_task_manager
        tm = get_task_manager()
        if tm:
            tm.shutdown()
    except Exception as e:
        logger.warning(f"定时任务调度器关闭异常: {e}")

    # 关闭 DuckDB 连接，刷 WAL 到主库
    try:
        from engine.data import get_data_engine
        store = get_data_engine().store
        try:
            store._conn.execute("CHECKPOINT")
        except Exception:
            pass
        store.close()
    except Exception as e:
        logger.warning(f"DuckDB 关闭异常: {e}")

    # 关闭 Main Agent DB
    try:
        from engine.agent.db import AgentDB
        AgentDB.get_instance().close()
    except Exception:
        pass

    # 关闭 Agent Brain 调度器
    try:
        from engine.agent.scheduler import AgentScheduler
        AgentScheduler.get_instance().shutdown()
    except Exception:
        pass

    logger.info("🌄  StockScape Engine 关闭")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await _startup()
    try:
        yield
    finally:
        await _shutdown()


# ─── 创建 FastAPI 应用 ─────────────────────────────────
app = FastAPI(
    title="StockScape Engine",
    description="A股多维聚类 3D 地形可视化平台 — 数据与算法引擎",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ─── CORS 中间件 ──────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.server.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── 请求耗时中间件 ──────────────────────────────────
@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    """记录每个请求的耗时，慢请求额外 warning"""
    start = time.monotonic()
    response = await call_next(request)
    elapsed = time.monotonic() - start
    path = request.url.path
    method = request.method
    status = response.status_code
    # 跳过健康检查等高频低价值路由
    if path not in ("/api/v1/health", "/", "/docs", "/redoc", "/openapi.json"):
        logger.info(f"⏱️ {method} {path} → {status} 耗时 {elapsed:.2f}s")
    if elapsed > 5.0:
        logger.warning(f"🐢 慢请求: {method} {path} 耗时 {elapsed:.1f}s")
    response.headers["X-Response-Time"] = f"{elapsed:.3f}s"
    return response

# ─── 注册路由 ─────────────────────────────────────────
app.include_router(data_router)
app.include_router(cluster_router)
app.include_router(chat_router)
app.include_router(quant_router)
app.include_router(analysis_router)
app.include_router(debate_router)
app.include_router(info_router)
app.include_router(expert_router)
app.include_router(industry_router)
app.include_router(sector_router)
app.include_router(create_agent_router(), prefix="/api/v1/agent")


# ─── 健康检查 ──────────────────────────────────────────
@app.get("/health")
@app.get("/api/v1/health")
async def global_health():
    """全局健康检查"""
    from engine.data import get_data_engine
    de = get_data_engine()
    health = de.health_check()
    return {
        "status": "ok",
        "engine": "StockScape",
        "version": "0.1.0",
        "stock_count": health.get("stock_count", 0),
    }


# ─── 应用 Bootstrap ──────────────────────────────────
@app.get("/api/v1/app/bootstrap")
async def app_bootstrap():
    """前端启动时调用 — 返回功能开关和服务器状态"""
    from llm.config import llm_settings

    return {
        "version": "0.1.0",
        "features": settings.features.model_dump(),
        "llm_enabled": bool(llm_settings.api_key),
    }


# ─── 用户认证端点 ─────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str | None = None


_USERNAME_RE = r'^[\w\u4e00-\u9fff]{1,32}$'


@app.post("/api/v1/app/login")
async def app_login(req: LoginRequest):
    """用户登录 — 验证密码，返回 JWT"""
    import re
    from auth import get_user, verify_password, update_last_login, create_jwt

    username = req.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="用户名不能为空")
    if not re.match(_USERNAME_RE, username):
        raise HTTPException(status_code=400, detail="无效的用户名格式（仅允许字母、数字、下划线、中文，1~32字符）")

    user = get_user(username)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")

    if not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="密码错误")

    update_last_login(username)
    token = create_jwt(username)

    return {
        "user_id": username,
        "display_name": user["display_name"],
        "token": token,
    }


@app.post("/api/v1/app/register")
async def app_register(req: RegisterRequest):
    """用户注册 — 创建用户，返回 JWT"""
    import re
    from auth import get_user, create_user, create_jwt, update_last_login

    username = req.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="用户名不能为空")
    if not re.match(_USERNAME_RE, username):
        raise HTTPException(status_code=400, detail="无效的用户名格式（仅允许字母、数字、下划线、中文，1~32字符）")
    if len(req.password) < 4:
        raise HTTPException(status_code=400, detail="密码至少 4 位")

    existing = get_user(username)
    if existing:
        raise HTTPException(status_code=409, detail="用户名已存在")

    user = create_user(username, req.password, req.display_name)
    update_last_login(username)
    token = create_jwt(username)

    return {
        "user_id": user["user_id"],
        "display_name": user["display_name"],
        "token": token,
    }


@app.get("/api/v1/app/users")
async def app_users():
    """获取用户列表（不含密码）"""
    from auth import list_users

    return {"users": list_users()}


# ─── 根路由 ────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "name": "StockScape Engine",
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
            "industry_health": "GET /api/v1/industry/health",
            "industry_analyze": "POST /api/v1/industry/analyze (SSE 流式)",
            "industry_cognition": "GET /api/v1/industry/cognition/{target}",
            "industry_mapping": "GET /api/v1/industry/mapping",
            "industry_capital": "GET /api/v1/industry/capital/{code}",
            "sector_boards": "GET /api/v1/sector/boards?type=industry",
            "sector_heatmap": "GET /api/v1/sector/heatmap?type=industry",
            "sector_rotation": "GET /api/v1/sector/rotation?days=10",
            "sector_fetch": "POST /api/v1/sector/fetch?type=industry",
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
