"""
Agent Brain 定时调度
每个交易日收盘后自动运行 AgentBrain
"""
from __future__ import annotations

from datetime import date

from loguru import logger


class AgentScheduler:
    """Agent Brain 定时调度器"""

    _instance: AgentScheduler | None = None
    _scheduler = None

    @classmethod
    def get_instance(cls) -> AgentScheduler:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._scheduler = None

    def start(self, portfolio_id: str | None = None):
        """启动定时调度"""
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.triggers.cron import CronTrigger

            self._scheduler = AsyncIOScheduler()
            self._scheduler.add_job(
                self._daily_run,
                CronTrigger(hour=15, minute=30, day_of_week="mon-fri"),
                id="agent_brain_daily",
                args=[portfolio_id],
                replace_existing=True,
            )
            self._scheduler.start()
            logger.info("🧠 Agent Brain 调度器已启动 (每交易日 15:30)")
        except ImportError:
            logger.warning("🧠 APScheduler 未安装，Agent Brain 定时调度不可用")
        except Exception as e:
            logger.warning(f"🧠 Agent Brain 调度器启动失败: {e}")

    async def _daily_run(self, portfolio_id: str | None = None):
        """每日定时运行"""
        today = date.today()
        if today.weekday() >= 5:
            logger.info("🧠 今天是周末，跳过 Agent Brain 运行")
            return

        if not portfolio_id:
            from engine.agent.db import AgentDB
            from engine.agent.service import AgentService
            from engine.agent.validator import TradeValidator
            db = AgentDB.get_instance()
            svc = AgentService(db=db, validator=TradeValidator())
            portfolios = await svc.list_portfolios()
            live = [p for p in portfolios if p.get("mode") == "live"]
            if not live:
                logger.info("🧠 没有 live 账户，跳过运行")
                return
            portfolio_id = live[0]["id"]

        logger.info(f"🧠 定时运行 AgentBrain: portfolio={portfolio_id}")

        from engine.agent.brain import AgentBrain
        from engine.agent.db import AgentDB
        from engine.agent.service import AgentService
        from engine.agent.validator import TradeValidator

        db = AgentDB.get_instance()
        svc = AgentService(db=db, validator=TradeValidator())
        run_record = await svc.create_brain_run(portfolio_id, "scheduled")

        brain = AgentBrain(portfolio_id)
        await brain.execute(run_record["id"])

    def shutdown(self):
        """关闭调度器"""
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            logger.info("🧠 Agent Brain 调度器已关闭")
