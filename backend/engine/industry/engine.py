"""IndustryEngine — 产业链引擎门面类

统一管理行业认知生成、行业→股票映射、资金构成分析。
数据源通过 DataEngine，LLM 推理通过 IndustryAgent，缓存在 DuckDB shared.* schema。
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from loguru import logger

from .market_bridge import CrossMarketBridge
from .schemas import IndustryCognition, IndustryMapping, CapitalStructure


class IndustryEngine:
    """产业链引擎 — 行业认知/映射/资金构成的门面"""

    def __init__(self, data_engine, llm_provider=None):
        self._data = data_engine
        self._store = data_engine.store
        self._llm = llm_provider
        self._agent = None  # 延迟初始化
        self._bridge = CrossMarketBridge()

    @property
    def agent(self):
        """延迟初始化 IndustryAgent（避免循环依赖）"""
        if self._agent is None:
            from .agent import IndustryAgent
            self._agent = IndustryAgent(self._llm, self._store)
        return self._agent

    # ── 行业认知 ──

    async def analyze(
        self,
        target: str,
        as_of_date: str = "",
        force_refresh: bool = False,
    ) -> IndustryCognition | None:
        """获取目标的行业产业链认知（缓存优先，未命中则 Agent 生成）

        Args:
            target: 股票代码或行业名
            as_of_date: 时间锚点
            force_refresh: 强制刷新缓存

        Returns:
            IndustryCognition 或 None（无行业信息时）
        """
        t0 = time.monotonic()
        industry, code = self._resolve_industry(target)
        if not industry:
            logger.info(f"无法识别行业: {target}")
            return None

        if not as_of_date:
            as_of_date = datetime.now(tz=ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")

        # 缓存检查
        if not force_refresh:
            cached = self._load_cached(industry, as_of_date)
            if cached:
                elapsed = time.monotonic() - t0
                logger.info(f"⏱️ IndustryEngine.analyze({industry}) 缓存命中 耗时 {elapsed:.1f}s")
                return cached

        # Agent 生成
        if not self._llm:
            logger.warning("LLM 未配置，无法生成行业认知")
            return None

        cognition = await self.agent.generate_cognition(
            industry=industry,
            target=code or target,
            as_of_date=as_of_date,
        )
        if cognition:
            self._save_cache(cognition)
        elapsed = time.monotonic() - t0
        logger.info(f"⏱️ IndustryEngine.analyze({industry}) 耗时 {elapsed:.1f}s, {'生成成功' if cognition else 'LLM未配置'}")
        return cognition

    # ── 行业映射 ──

    def get_industry_mapping(self) -> dict[str, list[str]]:
        """获取行业→股票代码映射（从 company_profiles 构建）"""
        profiles = self._data.get_profiles()
        mapping: dict[str, list[str]] = {}
        for code, info in profiles.items():
            industry = info.get("industry", "")
            if industry:
                mapping.setdefault(industry, []).append(code)
        return mapping

    def get_industry_stocks(self, industry: str) -> list[str]:
        """获取指定行业的全部股票代码"""
        mapping = self.get_industry_mapping()
        return mapping.get(industry, [])

    def get_stock_industry(self, code: str) -> str:
        """获取股票所属行业"""
        profile = self._data.get_profile(code)
        return profile.get("industry", "") if profile else ""

    def list_industries(self) -> list[IndustryMapping]:
        """列出所有行业及其股票数量"""
        mapping = self.get_industry_mapping()
        return [
            IndustryMapping(industry=ind, stocks=codes, stock_count=len(codes))
            for ind, codes in sorted(mapping.items(), key=lambda x: -len(x[1]))
        ]

    # ── 资金构成分析 ──

    async def get_capital_structure(self, code: str, as_of_date: str = "") -> CapitalStructure:
        """汇聚资金流向 + 北向持股 + 融资融券 + 换手率，构建结构化资金构成"""
        t0 = time.monotonic()
        from engine.arena.data_fetcher import DataFetcher
        fetcher = DataFetcher(as_of_date=as_of_date)

        money_flow, northbound, margin, turnover = await asyncio.gather(
            asyncio.to_thread(fetcher.get_money_flow, code),
            asyncio.to_thread(fetcher.get_northbound_holding, code),
            asyncio.to_thread(fetcher.get_margin_balance, code),
            asyncio.to_thread(fetcher.get_turnover_rate, code),
        )

        cs = CapitalStructure(code=code, as_of_date=as_of_date or fetcher.end_date)

        # 资金流向
        if "error" not in money_flow:
            cs.main_force_net_inflow = money_flow.get("主力净流入", "")
            cs.main_force_ratio = money_flow.get("主力净流入占比", "")
            cs.super_large_net_inflow = money_flow.get("超大单净流入", "")
            cs.large_net_inflow = money_flow.get("大单净流入", "")
            cs.small_net_inflow = money_flow.get("小单净流入", "")

        # 北向持股
        if "error" not in northbound:
            cs.northbound_shares = northbound.get("持股数量", "")
            cs.northbound_market_value = northbound.get("持股市值", "")
            cs.northbound_ratio = northbound.get("持股占比", "")
            cs.northbound_change = northbound.get("持股变化", "")

        # 融资融券
        if "error" not in margin:
            cs.margin_balance = margin.get("融资余额", "")
            cs.margin_buy = margin.get("融资买入额", "")
            cs.short_selling_volume = margin.get("融券余量", "")

        # 换手率
        if "error" not in turnover:
            cs.turnover_rate = turnover.get("turnover_rate", 0.0)

        # 构建摘要
        cs.structure_summary = self._build_capital_summary(cs)

        elapsed = time.monotonic() - t0
        logger.info(f"⏱️ IndustryEngine.get_capital_structure({code}) 耗时 {elapsed:.1f}s")
        return cs

    def _build_capital_summary(self, cs: CapitalStructure) -> str:
        """基于规则生成资金构成的文字摘要"""
        parts = []
        if cs.main_force_net_inflow:
            parts.append(f"主力净流入{cs.main_force_net_inflow}（占比{cs.main_force_ratio}）")
        if cs.northbound_ratio:
            parts.append(f"北向持股占比{cs.northbound_ratio}，变化{cs.northbound_change}")
        if cs.margin_balance:
            parts.append(f"融资余额{cs.margin_balance}")
        if cs.turnover_rate:
            parts.append(f"换手率{cs.turnover_rate:.2f}%")
        return "；".join(parts) if parts else "资金数据暂缺"

    # ── 健康检查 ──

    def health_check(self) -> dict:
        return {
            "status": "ok",
            "llm_available": self._llm is not None,
            "industry_count": len(self.get_industry_mapping()),
        }

    def bridge_market_assets(self, target: str, market: str = "", limit: int = 10) -> dict:
        return self._bridge.bridge(target, market=market, limit=limit)

    # ── 私有方法 ──

    def _resolve_industry(self, target: str) -> tuple[str, str]:
        """解析目标为 (行业名, 股票代码)"""
        import re
        target = target.strip()

        # 如果是 6 位数字，当作股票代码
        if re.fullmatch(r"\d{6}", target):
            profile = self._data.get_profile(target)
            if profile:
                return profile.get("industry", ""), target
            return "", target

        # 否则当作行业名，检查是否存在
        mapping = self.get_industry_mapping()
        if target in mapping:
            return target, ""

        # 模糊匹配行业名
        for ind in mapping:
            if target in ind or ind in target:
                return ind, ""

        # 常见行业别名/概念名 → 标准行业名映射
        INDUSTRY_ALIASES: dict[str, str] = {
            "新能源汽车": "汽车整车",
            "电力设备": "输配电气",
            "光伏": "光伏设备",
            "锂电": "电池",
            "锂电池": "电池",
            "固态电池": "电池",
            "储能": "电池",
            "芯片": "半导体",
            "AI": "计算机应用",
            "人工智能": "计算机应用",
            "白酒": "饮料制造",
            "军工": "航天航空",
            "国防军工": "航天航空",
            "医药": "化学制药",
            "生物医药": "化学制药",
            "消费电子": "消费电子",
            "机器人": "机械行业",
            "无人机": "航天航空",
            "券商": "证券",
            "保险": "保险",
            "银行": "银行",
            "地产": "房地产开发",
            "房地产": "房地产开发",
            "钢铁": "普钢",
            "煤炭": "煤炭开采",
            "石油": "油气开采",
            "石油开采": "油气开采",
            "有色": "小金属",
            "稀土": "小金属",
            "风电": "风电设备",
            "水电": "电力行业",
            "电力": "电力行业",
        }
        alias_target = INDUSTRY_ALIASES.get(target)
        if alias_target:
            logger.debug(f"行业别名解析: '{target}' → '{alias_target}'")
            return alias_target, ""

        # 概念性词汇黑名单 — 这些不是具体行业，无需识别
        _BLACKLIST = {"热点板块", "市场", "市场整体", "大盘", "板块", "概念", "题材", "全市场"}
        if target in _BLACKLIST:
            logger.debug(f"跳过非行业词汇: '{target}'")
            return "", ""

        # 尝试当作公司名查找股票代码，再通过代码查行业
        profiles = self._data.get_profiles()
        for code, info in profiles.items():
            name = info.get("name", "")
            if name and (target in name or name in target):
                industry = info.get("industry", "")
                if industry:
                    logger.debug(f"公司名解析行业: '{target}' → {code}({name}) → {industry}")
                    return industry, code

        return "", ""

    def _load_cached(self, industry: str, as_of_date: str) -> IndustryCognition | None:
        """从 DuckDB 读取缓存"""
        try:
            row = self._store._conn.execute(
                "SELECT cognition_json FROM shared.industry_cognition "
                "WHERE industry = ? AND as_of_date = ?",
                [industry, as_of_date],
            ).fetchone()
            if row:
                data = json.loads(row[0])
                return IndustryCognition(**data)
        except Exception as e:
            logger.debug(f"行业认知缓存读取失败: {e}")
        return None

    def _save_cache(self, cognition: IndustryCognition):
        """写入 DuckDB 缓存"""
        try:
            self._store._conn.execute(
                "INSERT OR REPLACE INTO shared.industry_cognition "
                "(industry, as_of_date, target, cognition_json) VALUES (?, ?, ?, ?)",
                [cognition.industry, cognition.as_of_date, cognition.target,
                 cognition.model_dump_json()],
            )
        except Exception as e:
            logger.warning(f"行业认知缓存写入失败: {e}")
