"""引擎专家 — 4 个引擎领域专家 + 1 个 RAG 投资顾问

每个引擎专家将用户问题路由到对应引擎工具链，
由 LLM 基于引擎返回数据生成流式回复。
"""

import asyncio
import json
import os
from typing import AsyncGenerator, Literal

import pandas as pd
from loguru import logger

# ─── LLM 原始输出调试开关 ───────────────────────────────
# 设置环境变量 LLM_DEBUG_RAW=true 可打印 LLM 的完整原始输出（含 <think> 等被过滤的内容）
# 注意：使用函数延迟读取，确保 .env 已加载
def _is_llm_debug_raw() -> bool:
    return os.environ.get("LLM_DEBUG_RAW", "").lower() in ("true", "1", "yes")


# 兼容：模块级常量（首次 import 时的快照），但关键路径用函数实时读取
LLM_DEBUG_RAW = _is_llm_debug_raw()
if LLM_DEBUG_RAW:
    logger.info("🔬 LLM_DEBUG_RAW 已开启 — 将打印 LLM 完整原始输出日志")

ExpertType = Literal["data", "quant", "info", "industry", "rag", "short_term"]

EXPERT_PROFILES: dict[str, dict] = {
    "data": {
        "name": "数据专家",
        "icon": "📊",
        "color": "#60A5FA",
        "description": "行情查询、股票搜索、聚类分析、全市场概览",
        "system_prompt": (
            "你是「老数」，A股顶级数据猎手，20年实战经验的私募数据总监。"
            "你信奉「数据不会说谎，但大多数人不会看数据」。\n\n"
            "## 你的人格\n"
            "- 你用数据说话，但从不含糊其辞。看到异常数据会直接指出：「这个量价背离很危险」「这个放量突破是真突破」\n"
            "- 你敢下判断。基于数据，你会明确说「建议关注」「建议回避」「可以考虑介入」\n"
            "- 你喜欢用数据对比来揭示机会：「同板块中，X的量价配合度远优于Y和Z」\n"
            "- 你对数据造假深恶痛绝，会直言不讳地指出异常\n\n"
            "## 主动扫描策略（开放式问题必须遵守）\n"
            "当用户问「推荐股票」「有什么机会」等开放式问题时，你**必须主动使用工具扫描全市场**：\n"
            "1. 先用 query_market_overview 看全市场涨跌概况\n"
            "2. 再用 run_screen 筛选异动股（如：涨幅>3%、换手率>3%）\n"
            "3. 对筛选出的候选股用 query_history 看近期走势确认\n"
            "**绝对不能只基于用户之前聊过的股票来推荐，必须从数据中发现新机会**\n\n"
            "## 输出风格\n"
            "- 用数据锤事实，用对比出结论\n"
            "- 必须给出明确的看法（看多/看空/中性）和信心等级（★~★★★★★）\n"
            "- 当数据足以支撑判断时，直接推荐具体标的，附带数据理由\n"
            "- 使用 Markdown 格式，善用表格展示数据对比\n"
            "- ⚠️ 末尾附简短风险提示（一句话即可，不要长篇大论的免责声明）"
        ),
        "suggestions": [
            "今日全市场概览",
            "搜索新能源相关股票",
            "查询聚类 0 的成分股",
            "帮我看看茅台的详情",
        ],
        "engines": ["data_engine"],
    },
    "quant": {
        "name": "量化专家",
        "icon": "🔬",
        "color": "#A78BFA",
        "description": "技术指标、因子评分、IC 回测、条件选股",
        "system_prompt": (
            "你是「Q神」，A股量化圈的传奇交易员，自建因子库超 200 个，年化夏普比 2.5+。"
            "你信奉「市场没有圣杯，但概率优势可以积累成必然」。\n\n"
            "## 你的人格\n"
            "- 你用概率和赔率思维做决策，从不说「不好说」「看情况」这种废话\n"
            "- 你会把技术信号翻译成明确的交易建议：「MACD底背离+RSI超卖，胜率72%，可以左侧建仓」\n"
            "- 你善于用因子评分给股票排名：「在同行业中，因子综合评分前3是：X、Y、Z」\n"
            "- 你对技术指标的解读总是伴随历史回测数据：「这个形态过去50次出现，37次后续上涨」\n"
            "- 你最痛恨模棱两可，认为「不敢下注的量化不如去做文员」\n\n"
            "## 主动选股策略（开放式问题必须遵守）\n"
            "当用户问「推荐股票」「有什么机会」等开放式问题时，你**必须主动使用选股工具**：\n"
            "1. 用 run_screen 做多因子筛选（如：PE<30、换手率>3%、涨幅>0%）\n"
            "2. 对筛选出的top候选股用 get_technical_indicators 确认技术信号\n"
            "3. 按量化评分排序，给出Top5推荐列表\n"
            "**绝对不能只谈理论，必须用工具找到具体标的**\n\n"
            "## 输出风格\n"
            "- 每个分析必须有明确结论：做多/做空/观望，附带胜率和目标位\n"
            "- 选股时直接给出排名列表，标注核心因子得分\n"
            "- 技术分析必须给具体价位：支撑位、阻力位、止损位、目标位\n"
            "- 使用 Markdown 格式，善用表格展示因子数据\n"
            "- ⚠️ 末尾附简短风险提示"
        ),
        "suggestions": [
            "贵州茅台的技术指标如何？",
            "查看因子体系全景",
            "PE 低于 20 且换手率大于 3% 的股票",
            "运行因子 IC 回测",
        ],
        "engines": ["quant_engine"],
    },
    "info": {
        "name": "资讯专家",
        "icon": "📰",
        "color": "#F59E0B",
        "description": "新闻情感、公告解读、事件影响评估",
        "system_prompt": (
            "你是「消息灵通哥」，前财经记者出身的私募投研总监，人脉横跨卖方研究所、产业资本和游资圈。"
            "你信奉「A股是政策市+资金市，消息面决定了短期80%的走势」。\n\n"
            "## 你的人格\n"
            "- 你嗅觉极其灵敏，善于从看似平淡的新闻中挖掘出投资机会\n"
            "- 你会直接判断消息的利好/利空程度（★~★★★★★），并给出受益标的\n"
            "- 你善于串联多条消息，揭示市场炒作主线：「这三条消息指向同一个方向——XX板块要起飞」\n"
            "- 你对公告解读毫不含糊：「这个定增方案就是利好，别被市场恐慌带偏了」\n"
            "- 你有自己的消息评估体系：政策 > 业绩 > 资金 > 事件 > 传闻\n\n"
            "## 主动扫描策略（开放式问题必须遵守）\n"
            "当用户问「推荐股票」「有什么机会」等开放式问题时，你**必须主动挖掘消息面机会**：\n"
            "1. 分析近期A股最重大的政策变化和行业新闻\n"
            "2. 找出有明确利好催化的行业和个股\n"
            "3. 关注被市场忽略的潜在机会（消息出了但股价还没反应）\n"
            "**不能只分析用户提到的股票，要主动发现新闻驱动的新机会**\n\n"
            "## 输出风格\n"
            "- 对每条重要消息给出影响评级和受益/受损标的\n"
            "- 善于发现隐藏的投资线索，主动推荐被市场忽略的机会\n"
            "- 事件驱动分析必须给出时间窗口和催化剂节点\n"
            "- 使用 Markdown 格式，消息按重要性排序\n"
            "- ⚠️ 末尾附简短风险提示"
        ),
        "suggestions": [
            "宁德时代最近有什么新闻？",
            "比亚迪近期公告",
            "评估降息对银行股的影响",
            "半导体行业最近的市场情绪如何？",
        ],
        "engines": ["info_engine"],
    },
    "industry": {
        "name": "产业链专家",
        "icon": "🏭",
        "color": "#10B981",
        "description": "行业认知、产业链映射、资金构成、周期分析",
        "system_prompt": (
            "你是「链主」，前头部券商行业首席分析师，深耕产业链研究15年，覆盖过6个行业的完整牛熊周期。"
            "你信奉「搞懂产业链就搞懂了股票的70%，剩下30%交给情绪」。\n\n"
            "## 你的人格\n"
            "- 你从产业链视角看股票，总能看到别人看不到的逻辑：「下游需求爆发 → 中游产能紧张 → 上游涨价」\n"
            "- 你会明确指出产业链中最具投资价值的环节和标的：「这个阶段，龙头是X，弹性最大的是Y」\n"
            "- 你对行业周期有精准判断：「现在是周期底部右侧，该贪婪不该恐惧」\n"
            "- 你善于辨别真龙头和伪龙头：「X只是市值最大，但真正的技术壁垒在Y」\n"
            "- 你看不起只看K线不看产业的人：「不懂产业的人永远只能追涨杀跌」\n\n"
            "## 主动分析策略（开放式问题必须遵守）\n"
            "当用户问「推荐股票」「有什么机会」等开放式问题时，你**必须主动分析板块和产业链**：\n"
            "1. 用 query_industry_mapping 获取当前板块全景\n"
            "2. 找出处于景气上行期或有政策催化的行业\n"
            "3. 用 query_industry_cognition 深入分析最有机会的2-3个板块\n"
            "4. 明确给出每个推荐板块的龙头股\n"
            "**不能只分析用户提过的行业，要从产业周期视角发现被忽略的机会**\n\n"
            "## 输出风格\n"
            "- 产业链分析必须落地到具体标的推荐，标注推荐理由\n"
            "- 行业周期判断必须给出明确位置（底部/复苏/繁荣/衰退）\n"
            "- 板块分析要给出龙头排序和各自的核心竞争力\n"
            "- 使用 Markdown 格式，善用产业链图谱和对比表格\n"
            "- ⚠️ 末尾附简短风险提示"
        ),
        "suggestions": [
            "半导体产业链分析",
            "锂电池行业现在处于什么周期？",
            "查看白酒行业板块成分股",
            "宁德时代的资金构成如何？",
        ],
        "engines": ["industry_engine"],
    },
    "rag": {
        "name": "投资顾问",
        "icon": "🧠",
        "color": "#EC4899",
        "description": "自由对话、知识图谱、信念系统、综合分析",
        "system_prompt": "",  # RAG 专家使用自己的 prompt 系统
        "suggestions": [
            "宁德时代近期走势如何？",
            "A 股政策面有什么变化？",
            "新能源板块值得关注吗？",
            "帮我做一份市场研判",
        ],
        "engines": ["expert_agent"],
    },
    "short_term": {
        "name": "短线专家",
        "icon": "⚡",
        "color": "#F97316",
        "description": "短线交易、技术面+资金流+板块联动、1-5日操作策略",
        "system_prompt": "",  # 短线专家使用 RAG Agent 的 persona 系统
        "suggestions": [
            "今天有什么短线机会？",
            "哪些板块在轮动？龙头是谁？",
            "分析一下这只票的短线买点",
            "主力资金在往哪个方向流？",
        ],
        "engines": ["expert_agent"],
    },
}


class EngineExpert:
    """引擎专家 — 基于引擎数据 + LLM 的流式对话"""

    # 类级缓存：名称→代码映射（懒加载）
    _name_to_code: dict[str, str] | None = None
    _snapshot_lock: asyncio.Lock | None = None  # 延迟初始化，避免在非事件循环上下文中创建

    @classmethod
    def _resolve_code(cls, raw: str) -> str:
        """将 LLM 传入的 code 参数解析为标准 6 位股票代码

        LLM 经常传股票名称（如"雄韬股份"）而非代码（"002733"），
        此方法自动解析名称→代码，保证下游数据引擎能正确查询。
        """
        raw = raw.strip()

        # 空字符串或过短的输入（单字无法可靠匹配），直接跳过
        if len(raw) < 2:
            if raw:
                logger.warning(f"无法解析股票代码(过短): '{raw}'")
            return raw

        # 非股票词汇黑名单 — 这些是 LLM 常见的概念性/泛化词汇
        _NON_STOCK_WORDS = {
            "市场", "市场整体", "大盘", "板块", "行业", "概念", "题材",
            "热点板块", "全市场", "指数", "整体", "沪深", "主板",
            "创业板", "科创板", "北交所",
        }
        if raw in _NON_STOCK_WORDS:
            logger.debug(f"跳过非股票词汇: '{raw}'")
            return raw

        # 已经是 6 位纯数字代码，直接返回
        if len(raw) == 6 and raw.isdigit():
            return raw

        # 懒加载名称→代码映射
        if cls._name_to_code is None:
            try:
                from engine.data import get_data_engine
                de = get_data_engine()
                profiles = de.get_profiles()
                cls._name_to_code = {}
                for code, info in profiles.items():
                    name = info.get("name", "")
                    if name:
                        cls._name_to_code[name] = code
                logger.info(f"EngineExpert 名称映射缓存已构建: {len(cls._name_to_code)} 条")
            except Exception as e:
                logger.warning(f"构建名称映射失败: {e}")
                cls._name_to_code = {}

        # 精确匹配
        if raw in cls._name_to_code:
            resolved = cls._name_to_code[raw]
            logger.debug(f"代码解析: '{raw}' → '{resolved}'")
            return resolved

        # 模糊匹配（名称包含输入）
        for name, code in cls._name_to_code.items():
            if raw in name or name in raw:
                logger.debug(f"代码模糊解析: '{raw}' → '{code}' ({name})")
                return code

        # 无法解析，原样返回（下游会报错但不会崩溃）
        logger.warning(f"无法解析股票代码: '{raw}'")
        return raw

    def __init__(self, expert_type: ExpertType, llm_provider=None):
        self.expert_type = expert_type
        self.profile = EXPERT_PROFILES[expert_type]
        self._llm = llm_provider

    @classmethod
    async def _ensure_snapshot(cls, de) -> "pd.DataFrame":
        """确保快照数据可用且不过期 — 如果为空或过期，自动拉取全市场行情并保存

        过期判断（交易时段 9:15~15:35）：
        - 快照为空 → 刷新
        - 快照 updated_at 早于今天 9:15（隔夜数据）→ 刷新
        - 快照 updated_at 距今超过 snapshot_refresh_minutes（默认30分钟）→ 刷新
        - 非交易时段（收盘后、周末）不刷新，使用上次快照即可

        使用类级别锁避免多个专家并发触发重复拉取。

        Returns:
            快照 DataFrame（可能为空，表示拉取也失败了）
        """
        import asyncio
        import datetime
        from config import settings

        refresh_minutes = settings.datasource.snapshot_refresh_minutes

        snap = de.get_snapshot()

        # 判断快照是否过期
        need_refresh = False
        if snap is None or snap.empty:
            need_refresh = True
        elif "updated_at" in snap.columns:
            now = datetime.datetime.now()
            # 交易日（周一~周五）且在 9:15~15:35 之间，检查快照新鲜度
            if now.weekday() < 5 and datetime.time(9, 15) <= now.time() <= datetime.time(15, 35):
                try:
                    latest_update = pd.to_datetime(snap["updated_at"]).max()
                    today_start = datetime.datetime.combine(now.date(), datetime.time(9, 15))
                    if latest_update < today_start:
                        # 隔夜数据，必须刷新
                        need_refresh = True
                        logger.info(
                            f"📡 快照已过期(隔夜): updated_at={latest_update}, "
                            f"today_start={today_start}, 需要刷新"
                        )
                    else:
                        # 盘中 TTL 检查：超过 refresh_minutes 分钟则刷新
                        age_minutes = (now - latest_update).total_seconds() / 60
                        if age_minutes > refresh_minutes:
                            need_refresh = True
                            logger.info(
                                f"📡 快照盘中过期: 已过 {age_minutes:.0f} 分钟 "
                                f"(TTL={refresh_minutes}min), 自动刷新"
                            )
                except Exception as e:
                    logger.warning(f"📡 快照时间检测异常(忽略): {e}")

        if not need_refresh:
            return snap

        # 需要刷新 — 用锁保护只拉取一次
        if cls._snapshot_lock is None:
            cls._snapshot_lock = asyncio.Lock()
        async with cls._snapshot_lock:
            # double-check：拿到锁后再检查一次（另一个协程可能已完成拉取）
            snap = de.get_snapshot()
            if snap is not None and not snap.empty and "updated_at" in snap.columns:
                now = datetime.datetime.now()
                try:
                    latest_update = pd.to_datetime(snap["updated_at"]).max()
                    age_minutes = (now - latest_update).total_seconds() / 60
                    if age_minutes <= refresh_minutes:
                        return snap  # 另一个协程已完成刷新，数据足够新
                except Exception:
                    if not snap.empty:
                        return snap
            try:
                logger.info("📡 快照为空或已过期，自动拉取全市场行情...")
                fresh = await asyncio.to_thread(de.get_realtime_quotes)
                if fresh is not None and not fresh.empty:
                    await asyncio.to_thread(de.save_snapshot, fresh)
                    logger.info(f"📡 自动拉取快照成功: {len(fresh)} 条")
                    return fresh
            except Exception as e:
                logger.warning(f"📡 自动拉取快照失败: {e}")
        # 拉取失败，退回旧快照（有总比没有好）
        return snap if snap is not None else __import__("pandas").DataFrame()

    async def chat(
        self, message: str, history: list[dict] | None = None,
        deep_think: bool = False, max_rounds: int = 3,
    ) -> AsyncGenerator[dict, None]:
        """流式对话，yield SSE 事件

        Args:
            deep_think: 多轮渐进模式 — 每轮工具执行完后 LLM 可以决定是否继续补查
            max_rounds: deep_think 模式下最大工具调用轮数（1~5）
        """
        if not self._llm:
            yield {"event": "error", "data": {"message": "LLM 未配置"}}
            return

        yield {"event": "thinking_start", "data": {}}

        # ══════════════════════════════════════════════════════
        # 多轮渐进工具调用循环
        # deep_think=False 时等同于原来的单轮（max 1 轮）
        # deep_think=True 时 LLM 看到上一轮数据后可以决定继续补查
        # ══════════════════════════════════════════════════════
        effective_max_rounds = max_rounds if deep_think else 1
        all_tool_results: list[str] = []   # 所有轮次累积的工具结果
        all_data_fetch_log: list[dict] = []
        round_num = 0

        while round_num < effective_max_rounds:
            round_num += 1

            # ── 通知前端当前轮次（deep_think 模式下） ──
            if deep_think:
                yield {"event": "thinking_round", "data": {
                    "round": round_num,
                    "max_rounds": effective_max_rounds,
                }}

            # 1. 规划工具调用（优先原生 Tool Use，fallback 到 prompt 方式）
            if round_num == 1:
                tool_plan = await self._plan_tools_dispatch(message)
            else:
                # 后续轮次：带上之前的工具结果，让 LLM 决定是否继续
                tool_plan = await self._plan_tools_with_context(
                    message, all_tool_results, round_num
                )
                if not tool_plan.get("tool_calls"):
                    logger.info(
                        f"🏁 [{self.expert_type}] deep_think 第{round_num}轮: "
                        f"LLM 认为数据充足，停止补查"
                    )
                    break

            tool_calls = tool_plan.get("tool_calls", [])
            if not tool_calls:
                break  # 无工具调用，直接进入回复

            # 2. 执行工具调用（含智能重试）
            round_results: list[str] = []
            for tc in tool_calls:
                if not isinstance(tc, dict):
                    logger.warning(f"跳过非dict工具调用: {type(tc)}")
                    continue
                action_name = tc.get("action", "unknown")
                params = tc.get("params", {})
                yield {"event": "tool_call", "data": {
                    "engine": tc.get("engine", self.expert_type),
                    "action": action_name,
                    "params": params,
                    "round": round_num if deep_think else None,
                }}
                result = await self._execute_tool(tc)

                # ── 智能重试：检测失败/空结果，让 LLM 修正参数后重试一次 ──
                is_failure = self._is_tool_result_failure(result)
                is_empty = self._is_tool_result_empty(result)
                if is_failure:
                    all_data_fetch_log.append({
                        "action": action_name, "params": params,
                        "status": "FAIL", "reason": result[:200],
                        "retried": True, "round": round_num,
                    })
                    logger.warning(f"🔄 [{self.expert_type}] R{round_num} {action_name} 首次失败，尝试智能重试: {result[:150]}")
                    retried_tc = await self._retry_with_fix(tc, result, message)
                    if retried_tc and retried_tc != tc:
                        retry_result = await self._execute_tool(retried_tc)
                        retry_is_failure = self._is_tool_result_failure(retry_result)
                        if not retry_is_failure:
                            logger.info(f"✅ [{self.expert_type}] R{round_num} {action_name} 重试成功"
                                        f" (原参数={params}, 新参数={retried_tc.get('params', {})})")
                            all_data_fetch_log.append({
                                "action": action_name,
                                "params": retried_tc.get("params", {}),
                                "status": "OK_RETRY", "reason": "",
                                "retried": True, "round": round_num,
                            })
                            result = retry_result
                        else:
                            logger.warning(f"❌ [{self.expert_type}] R{round_num} {action_name} 重试仍失败: {retry_result[:150]}")
                            all_data_fetch_log.append({
                                "action": action_name,
                                "params": retried_tc.get("params", {}),
                                "status": "FAIL_RETRY", "reason": retry_result[:200],
                                "retried": True, "round": round_num,
                            })
                    else:
                        logger.warning(f"❌ [{self.expert_type}] R{round_num} {action_name} LLM 无法修正参数，放弃重试")
                elif is_empty:
                    all_data_fetch_log.append({
                        "action": action_name, "params": params,
                        "status": "EMPTY", "reason": result[:200],
                        "retried": False, "round": round_num,
                    })
                    logger.debug(f"📭 [{self.expert_type}] R{round_num} {action_name} 数据为空(正常): {result[:100]}")
                else:
                    all_data_fetch_log.append({
                        "action": action_name, "params": params,
                        "status": "OK", "reason": "",
                        "retried": False, "round": round_num,
                    })

                round_results.append(result)
                tool_result_data = {
                    "engine": tc.get("engine", self.expert_type),
                    "action": action_name,
                    "summary": result[:200] if result else "无结果",
                    "round": round_num if deep_think else None,
                }
                # K 线数据：query_history / query_hourly 返回 chartData
                if action_name in ("query_history", "query_hourly") and result:
                    try:
                        parsed = json.loads(result)
                        if "records" in parsed:
                            tool_result_data["chartData"] = {
                                "code": parsed.get("code", ""),
                                "records": parsed["records"],
                            }
                    except (json.JSONDecodeError, KeyError):
                        pass
                # 数据校验结果：附带到前端
                if result and "_validation" in result:
                    try:
                        parsed_for_val = json.loads(result)
                        if "_validation" in parsed_for_val:
                            tool_result_data["validation"] = parsed_for_val["_validation"]
                    except (json.JSONDecodeError, Exception):
                        pass
                yield {"event": "tool_result", "data": tool_result_data}

            all_tool_results.extend(round_results)

            # 单轮模式直接跳出
            if not deep_think:
                break

            logger.info(
                f"🔄 [{self.expert_type}] deep_think 第{round_num}轮完成, "
                f"本轮获取 {len(round_results)} 条数据, 累计 {len(all_tool_results)} 条"
            )

        tool_results = all_tool_results

        # ── 数据获取可观测性日志 ──
        if all_data_fetch_log:
            ok_count = sum(1 for d in all_data_fetch_log if d["status"].startswith("OK"))
            fail_count = sum(1 for d in all_data_fetch_log if d["status"].startswith("FAIL"))
            empty_count = sum(1 for d in all_data_fetch_log if d["status"] == "EMPTY")
            retry_count = sum(1 for d in all_data_fetch_log if d["retried"])
            rounds_used = max((d.get("round", 1) for d in all_data_fetch_log), default=1)
            logger.info(
                f"📊 [{self.expert_type}] 数据获取统计: "
                f"轮数={rounds_used}, 总计={len(all_data_fetch_log)}, 成功={ok_count}, "
                f"空数据={empty_count}, 失败={fail_count}, 重试={retry_count}"
            )
            for entry in all_data_fetch_log:
                if entry["status"].startswith("FAIL"):
                    logger.warning(
                        f"📊 [{self.expert_type}] 数据获取失败详情: "
                        f"R{entry.get('round', '?')} action={entry['action']}, "
                        f"params={entry['params']}, reason={entry['reason']}"
                    )

        # 3. 提取数据校验摘要（_validation 字段由 DataValidator 注入）
        validation_summary = self._extract_validation_summary(tool_results)

        # 4. 流式生成回复
        # ── DEBUG: 记录传给 LLM 的工具数据摘要 ──
        if LLM_DEBUG_RAW and tool_results:
            for i, tr in enumerate(tool_results):
                logger.info(
                    f"🔬 [{self.expert_type}] LLM输入 tool_result[{i}] "
                    f"(长度={len(tr)}字): {tr[:500]}{'...(截断)' if len(tr) > 500 else ''}"
                )

        full_text = ""
        async for token, accumulated in self._reply_stream(
            message, tool_results, history=history, validation_summary=validation_summary
        ):
            full_text = accumulated
            yield {"event": "reply_token", "data": {"token": token}}

        # ── 回退机制：回复过短 / 内容是垃圾（工具调用代码）/ 明显不完整 → 非流式重生成 ──
        def _needs_retry(text: str) -> str | None:
            """检测回复是否需要重生成，返回原因或 None"""
            stripped = text.strip()
            if not stripped and tool_results:
                return "空回复"
            if not stripped and not tool_results:
                # 没有工具数据 + 回复为空 → LLM 可能输出了全是 [TOOL_CALL] 幻觉被过滤
                return "空回复(无工具数据，可能是幻觉工具调用被过滤)"
            if len(stripped) < 200 and tool_results:
                return f"回复过短({len(stripped)}字)"
            # 检测内容是否是工具调用垃圾（TOOL_CALL / tool_call 占比过高）
            import re
            clean = re.sub(r'\[TOOL_CALL\].*?\[/TOOL_CALL\]', '', stripped, flags=re.DOTALL)
            clean = re.sub(r'<tool_call>.*?</tool_call>', '', clean, flags=re.DOTALL)
            clean = re.sub(r'\{tool\s*=>', '', clean)
            if len(clean.strip()) < 50 and len(stripped) > 50:
                return f"内容主要是工具调用代码(有效内容仅{len(clean.strip())}字)"
            # 检测以冒号/省略号结尾（明显不完整）
            if stripped.endswith(("：", ":", "...", "…")) and len(stripped) < 300:
                return f"回复明显不完整(以'{stripped[-1]}'结尾)"
            return None

        retry_reason = _needs_retry(full_text)
        if retry_reason:
            logger.warning(
                f"⚠️ [{self.expert_type}] {retry_reason}，"
                f"触发非流式重生成 (tool_results={len(tool_results)}条)"
            )
            try:
                retry_text = await self._retry_reply_non_stream(
                    message, tool_results, history=history, validation_summary=validation_summary
                )
                if retry_text and len(retry_text.strip()) > len(full_text.strip()):
                    # 用新回复替换旧的
                    delta = retry_text[len(full_text):] if retry_text.startswith(full_text) else retry_text
                    if delta:
                        full_text = retry_text
                        yield {"event": "reply_token", "data": {"token": delta}}
            except Exception as e:
                logger.error(f"非流式重生成失败: {e}")

        yield {"event": "reply_complete", "data": {"full_text": full_text}}

    @staticmethod
    def _parse_tool_call_tags(raw_text: str) -> dict:
        """兜底解析 [TOOL_CALL] / <tool_call> 幻觉格式 → 标准 tool_calls

        当 LLM 没有输出期望的 JSON 格式，而是输出了类似：
          [TOOL_CALL] {tool => "run_screen", args => {...}} [/TOOL_CALL]
        时，从中提取工具名和参数，转换为标准格式。
        """
        import re
        tool_calls = []

        # 匹配 [TOOL_CALL]...[/TOOL_CALL] 和 <tool_call>...</tool_call>
        patterns = [
            re.findall(r'\[TOOL_CALL\](.*?)\[/TOOL_CALL\]', raw_text, re.DOTALL),
            re.findall(r'<tool_call>(.*?)</tool_call>', raw_text, re.DOTALL),
        ]
        blocks = [b for group in patterns for b in group]

        # 也匹配未闭合的 [TOOL_CALL]（LLM 可能忘了闭合）
        if not blocks:
            unclosed = re.findall(r'\[TOOL_CALL\](.*?)(?:\[/TOOL_CALL\]|$)', raw_text, re.DOTALL)
            blocks.extend(unclosed)

        for block in blocks:
            block = block.strip()
            if not block:
                continue

            # 方式1: 尝试直接解析 JSON（有些 LLM 在标签内写的就是 JSON）
            try:
                data = json.loads(block)
                if isinstance(data, dict):
                    action = data.get("action") or data.get("tool") or data.get("name", "")
                    params = data.get("params") or data.get("args") or data.get("arguments", {})
                    if action:
                        tool_calls.append({"action": action, "params": params if isinstance(params, dict) else {}})
                        continue
            except (json.JSONDecodeError, Exception):
                pass

            # 方式2: 解析 {tool => "xxx", args => {...}} 这种箭头格式
            tool_match = re.search(r'(?:tool|name|action)\s*(?:=>|:)\s*["\']?(\w+)["\']?', block, re.IGNORECASE)
            if not tool_match:
                continue

            action = tool_match.group(1)

            # 提取 args/params 部分 — 尝试找到 JSON 对象
            args_match = re.search(r'(?:args|params|arguments)\s*(?:=>|:)\s*(\{.*\})', block, re.DOTALL)
            params = {}
            if args_match:
                try:
                    params = json.loads(args_match.group(1))
                except (json.JSONDecodeError, Exception):
                    # 尝试修复常见的非标准 JSON（如 --key value 格式）
                    pass

            tool_calls.append({"action": action, "params": params if isinstance(params, dict) else {}})

        if tool_calls:
            logger.info(f"🔧 _parse_tool_call_tags 兜底解析成功: {len(tool_calls)} 个工具调用")
        return {"tool_calls": tool_calls}

    async def _plan_tools_with_context(
        self, message: str, previous_results: list[str], round_num: int,
    ) -> dict:
        """多轮渐进模式：带上之前工具结果，让 LLM 决定是否需要继续补查

        返回 {"tool_calls": [...]} 或 {"tool_calls": []}（表示数据充足）
        """
        import re
        from llm.providers import ChatMessage
        from engine.expert.personas import get_current_date_context

        tools_desc = self._get_available_tools_desc()

        # 将之前的工具结果摘要（每条截断到 500 字以防上下文爆炸）
        results_summary = "\n---\n".join(
            r[:500] + ("...(截断)" if len(r) > 500 else "")
            for r in previous_results
        )

        plan_prompt = f"""你是{self.profile['name']}。用户的问题是：「{message}」

⏰ 当前时间：{get_current_date_context()}

你已经进行了 {round_num - 1} 轮数据查询，获得了以下数据：
{results_summary}

请判断：基于已有数据，你能否给出一个**全面、深入、有具体结论**的分析回复？

- 如果已有数据足够回答用户问题，返回空列表：{{"tool_calls": []}}
- 如果还需要补充数据才能给出深入分析（例如：看到筛选结果后想查某只票的详情、看到个股后想查K线确认趋势），返回需要补查的工具调用

可用工具:
{tools_desc}

请以 JSON 格式回复:
{{
  "reasoning": "简述你为什么需要/不需要继续查数据",
  "tool_calls": [
    {{"action": "工具名", "params": {{"参数名": "值"}}}}
  ]
}}

注意：
- 不要重复查询已有的数据（避免死循环）
- 最多再查 2-3 个工具，聚焦在最关键的补充信息上
- 直接输出 JSON，不要包含 markdown 代码块。"""

        try:
            chunks: list[str] = []
            async for token in self._llm.chat_stream([
                ChatMessage("system", plan_prompt),
                ChatMessage("user", f"第{round_num}轮工具规划（之前已查 {len(previous_results)} 条数据）"),
            ]):
                chunks.append(token)
            text = "".join(chunks).strip()

            if _is_llm_debug_raw():
                logger.info(
                    f"🔬 [{self.expert_type}] _plan_tools_with_context R{round_num} "
                    f"原始输出(前500): {text[:500]}"
                )

            # 剥离 think 标签
            raw_text = text  # 保存原始文本用于兜底
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            text = re.sub(r"<minimax:.*?</minimax:[^>]+>", "", text, flags=re.DOTALL).strip()

            # 提取 JSON
            md_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
            if md_match:
                text = md_match.group(1).strip()

            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                # 防御：LLM 可能返回 list 而非 dict
                if isinstance(data, list):
                    logger.info(f"🧠 [{self.expert_type}] R{round_num} LLM 返回 list，自动包装")
                    for tc in data:
                        if isinstance(tc, dict) and "engine" not in tc:
                            tc["engine"] = self.expert_type
                    return {"tool_calls": data}
                reasoning = data.get("reasoning", "")
                tool_calls = data.get("tool_calls", [])
                if reasoning:
                    logger.info(f"🧠 [{self.expert_type}] R{round_num} 补查理由: {reasoning}")
                # 注入 engine 字段
                for tc in tool_calls:
                    if "engine" not in tc:
                        tc["engine"] = self.expert_type
                return {"tool_calls": tool_calls}

            # 兜底: 尝试从 [TOOL_CALL] / <tool_call> 幻觉格式中提取
            if "[TOOL_CALL]" in raw_text or "<tool_call>" in raw_text:
                fallback = self._parse_tool_call_tags(raw_text)
                if fallback["tool_calls"]:
                    logger.info(
                        f"🔧 [{self.expert_type}] _plan_tools_with_context R{round_num}: "
                        f"从 [TOOL_CALL] 标签兜底恢复 {len(fallback['tool_calls'])} 个工具调用"
                    )
                    for tc in fallback["tool_calls"]:
                        if "engine" not in tc:
                            tc["engine"] = self.expert_type
                    return fallback

        except Exception as e:
            logger.warning(f"_plan_tools_with_context R{round_num} 异常: {e}")

        return {"tool_calls": []}

    async def _plan_tools_dispatch(self, message: str) -> dict:
        """工具规划调度器 — 优先使用原生 Tool Use，失败时 fallback 到 prompt 方式

        原生 Tool Use 的优势：
        - 省掉一次独立的 LLM plan 调用（模型直接在响应中结构化返回工具调用）
        - 消除 JSON 解析失败、<think> 标签污染等问题
        - MiniMax M2.7 原生支持 OpenAI tools 协议
        """
        if self._llm and getattr(self._llm, "supports_tool_use", False):
            try:
                result = await self._plan_tools_native(message)
                if result.get("tool_calls"):
                    logger.info(
                        f"🚀 [{self.expert_type}] 原生 Tool Use 规划成功: "
                        f"{len(result['tool_calls'])} 个工具调用"
                    )
                    return result
                # 原生返回空 tool_calls — 也是合法的（不需要工具）
                logger.info(f"🚀 [{self.expert_type}] 原生 Tool Use: 无需调用工具")
                return result
            except Exception as e:
                logger.warning(
                    f"⚠️ [{self.expert_type}] 原生 Tool Use 失败，fallback 到 prompt 方式: {e}"
                )
        # Fallback: prompt 方式规划
        return await self._plan_tools(message)

    async def _plan_tools_native(self, message: str) -> dict:
        """使用原生 Function Calling (OpenAI tools 协议) 规划工具调用

        一次 LLM 调用即可完成工具规划，不需要额外的 plan 步骤。
        模型会在 response.tool_calls 中结构化返回工具调用。
        """
        import json as _json
        from llm.providers import ChatMessage
        from engine.expert.personas import get_current_date_context
        from engine.expert.skill_registry import SkillRegistry

        tools_schema = SkillRegistry.get_tools_schema(self.expert_type)
        if not tools_schema:
            return {"tool_calls": []}

        expert_name = self.profile["name"]
        expert_desc = self.profile.get("description", "")
        date_ctx = get_current_date_context()

        system_prompt = (
            f"你是{expert_name}。{expert_desc}\n"
            f"⏰ 当前时间：{date_ctx}\n\n"
            "用户提出了一个问题，请根据问题决定是否需要调用工具获取数据。\n"
            '注意：当用户提到"今天"、"最近"、"本周"等相对时间时，请根据上方的当前时间来理解。'
        )

        messages = [
            ChatMessage("system", system_prompt),
            ChatMessage("user", message),
        ]

        result = await self._llm.chat_with_tools(messages, tools=tools_schema)

        if LLM_DEBUG_RAW:
            logger.info(
                f"🔬 [{self.expert_type}] _plan_tools_native 返回: "
                f"content={len(result.content)}字, tool_calls={len(result.tool_calls)}个"
            )
            if result.tool_calls:
                for tc in result.tool_calls:
                    logger.info(
                        f"  📎 {tc['function']['name']}({tc['function']['arguments']})"
                    )

        if not result.tool_calls:
            return {"tool_calls": []}

        # 将 OpenAI tool_calls 格式转换为内部格式
        tool_calls = []
        for tc in result.tool_calls:
            func = tc.get("function", {})
            name = func.get("name", "")
            try:
                params = _json.loads(func.get("arguments", "{}"))
            except (_json.JSONDecodeError, Exception):
                params = {}

            tool_calls.append({
                "action": name,
                "params": params if isinstance(params, dict) else {},
                "engine": self.expert_type,
                # 保存原始 tool_call_id，用于后续多轮对话
                "_tool_call_id": tc.get("id", ""),
            })

        return {"tool_calls": tool_calls}

    async def _plan_tools(self, message: str) -> dict:
        """让 LLM 规划需要调用的工具（流式收集 + think 标签剥离）"""
        import re
        from llm.providers import ChatMessage
        from engine.expert.personas import get_current_date_context

        tools_desc = self._get_available_tools_desc()
        plan_prompt = f"""你是{self.profile['name']}。用户提出了一个问题，你需要决定是否需要调用工具获取数据。

⏰ 当前时间：{get_current_date_context()}

可用工具:
{tools_desc}

请以 JSON 格式回复:
{{
  "tool_calls": [
    {{"action": "工具名", "params": {{"参数名": "值"}}}}
  ]
}}

如果不需要工具，返回空列表:
{{"tool_calls": []}}

注意：当用户提到"今天"、"最近"、"本周"等相对时间时，请根据上方的当前时间来理解。
直接输出 JSON，不要包含 markdown 代码块、不要包含任何额外文字。
绝对不要输出 <think> 标签或任何思考过程，只输出纯 JSON。"""

        raw_text = ""  # 提前声明，避免 except 块中 UnboundLocalError
        try:
            # 流式收集（保持链路活跃）
            chunks: list[str] = []
            async for token in self._llm.chat_stream([
                ChatMessage("system", plan_prompt),
                ChatMessage("user", message),
            ]):
                chunks.append(token)
            text = "".join(chunks).strip()

            # ── DEBUG: 记录工具规划阶段的 LLM 原始输出 ──
            if LLM_DEBUG_RAW:
                logger.info(
                    f"🔬 [{self.expert_type}] _plan_tools 原始输出 "
                    f"(长度={len(text)}字):\n{text}"
                )

            if not text:
                logger.warning("工具规划 LLM 返回空内容，跳过工具调用")
                return {"tool_calls": []}

            # 保存原始文本（用于后续从 think 内容中提取 JSON）
            raw_text = text

            # 剥离各种可能的标签
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            text = re.sub(r"<minimax:.*?</minimax:[^>]+>", "", text, flags=re.DOTALL).strip()
            text = re.sub(r"<tool_call>.*?</tool_call>", "", text, flags=re.DOTALL).strip()
            text = re.sub(r"<tool_code>.*?</tool_code>", "", text, flags=re.DOTALL).strip()

            # 如果剥离 think 后为空，尝试从 think 内容中提取 JSON
            if not text:
                think_match = re.search(r"<think>(.*?)</think>", raw_text, re.DOTALL)
                if think_match:
                    think_content = think_match.group(1).strip()
                    # 尝试从 think 内容中找到 JSON 对象
                    json_match = re.search(r'\{[^{}]*"tool_calls"\s*:\s*\[.*?\]\s*\}', think_content, re.DOTALL)
                    if json_match:
                        text = json_match.group(0)
                        logger.info("工具规划: 从 <think> 标签内提取到 JSON")

            # 提取 JSON（处理 markdown 代码块）
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            # 尝试解析 JSON
            if not text:
                # 最后兜底：从原始文本中尝试提取任何 JSON 对象
                json_match = re.search(r'\{[^{}]*"tool_calls"\s*:\s*\[.*?\]\s*\}', raw_text, re.DOTALL)
                if json_match:
                    text = json_match.group(0)
                    logger.info("工具规划: 从原始文本兜底提取到 JSON")
                else:
                    # 兜底: 尝试从 [TOOL_CALL] / <tool_call> 幻觉格式中提取
                    if "[TOOL_CALL]" in raw_text or "<tool_call>" in raw_text:
                        fallback = self._parse_tool_call_tags(raw_text)
                        if fallback["tool_calls"]:
                            logger.info(
                                f"🔧 [{self.expert_type}] _plan_tools: "
                                f"JSON 提取全失败，从 [TOOL_CALL] 标签兜底恢复 "
                                f"{len(fallback['tool_calls'])} 个工具调用"
                            )
                            return fallback
                    return {"tool_calls": []}

            # 先尝试直接解析
            try:
                parsed = json.loads(text)
                # 防御：LLM 可能返回纯 list（如 [{...}]）而非 {"tool_calls": [...]}
                if isinstance(parsed, list):
                    logger.info(f"工具规划: LLM 返回了 list 而非 dict，自动包装为 tool_calls")
                    return {"tool_calls": parsed}
                if isinstance(parsed, dict):
                    return parsed
                # 其他类型（str, int 等）→ 跳过
                logger.warning(f"工具规划: json.loads 返回了意外类型 {type(parsed).__name__}")
                return {"tool_calls": []}
            except json.JSONDecodeError as je:
                # "Extra data" 说明 LLM 返回了多个连续 JSON 对象，提取第一个含 tool_calls 的
                if "Extra data" in str(je) or "Expecting value" in str(je):
                    logger.info(f"工具规划: JSON 解析遇到 '{je}'，尝试正则提取")
                    # 用贪婪匹配提取完整的 tool_calls JSON（支持嵌套大括号）
                    tc_match = re.search(
                        r'\{\s*"tool_calls"\s*:\s*\[.*?\]\s*(?:,\s*"[^"]*"\s*:\s*(?:"[^"]*"|[^,}]*))*\s*\}',
                        text, re.DOTALL
                    )
                    if tc_match:
                        extracted = tc_match.group(0)
                        logger.info(f"工具规划: 正则提取成功，长度={len(extracted)}")
                        return json.loads(extracted)
                    # 再试一种更宽松的匹配
                    tc_match2 = re.search(r'\{[^{}]*"tool_calls"\s*:\s*\[.*?\]\s*\}', text, re.DOTALL)
                    if tc_match2:
                        return json.loads(tc_match2.group(0))
                raise
        except Exception as e:
            logger.warning(f"工具规划失败，尝试 [TOOL_CALL] 兜底: {e}")
            # 最终兜底: 如果 JSON 解析全部失败，尝试从 [TOOL_CALL] 标签中恢复
            if "[TOOL_CALL]" in raw_text or "<tool_call>" in raw_text:
                fallback = self._parse_tool_call_tags(raw_text)
                if fallback["tool_calls"]:
                    logger.info(
                        f"🔧 [{self.expert_type}] _plan_tools: "
                        f"JSON 解析异常后从标签兜底恢复 "
                        f"{len(fallback['tool_calls'])} 个工具调用"
                    )
                    return fallback
            return {"tool_calls": []}

    @staticmethod
    def _is_tool_result_failure(result: str) -> bool:
        """判断工具结果是否为真正的失败（需要重试）。

        "数据为空"（如某个股近7天无公告）不算失败，不应触发重试。
        只有参数错误、接口异常等真正的错误才需要重试。

        约定:
        - {"error": "..."} → 真正的错误（参数不对、接口挂了），触发重试
        - {"empty": true, "note": "..."} → 数据为空（正常现象），不触发重试
        """
        if not result:
            return True

        # JSON 结构判断（优先）
        try:
            data = json.loads(result)
            if isinstance(data, dict):
                # 显式标记为"空数据"的，不算失败
                if data.get("empty"):
                    return False
                # 显式标记为错误的
                if "error" in data:
                    return True
        except (json.JSONDecodeError, Exception):
            pass

        # 纯文本关键词匹配（兜底，用于非 JSON 返回）
        fail_keywords = [
            "工具调用失败", "无法解析", "无法识别",
            "object is not subscriptable", "需要具体股票代码",
        ]
        result_lower = result[:300].lower()
        return any(kw.lower() in result_lower for kw in fail_keywords)

    @staticmethod
    def _is_tool_result_empty(result: str) -> bool:
        """判断工具结果是否为"数据为空"（正常现象，不需要重试）"""
        if not result:
            return False
        try:
            data = json.loads(result)
            if isinstance(data, dict) and data.get("empty"):
                return True
        except (json.JSONDecodeError, Exception):
            pass
        return False

    async def _retry_with_fix(self, failed_tc: dict, error_msg: str, original_question: str) -> dict | None:
        """让 LLM 根据错误信息修正工具参数，返回修正后的 tool_call dict，或 None"""
        if not self._llm:
            return None
        import re
        from llm.providers import ChatMessage

        action = failed_tc.get("action", "")
        params = failed_tc.get("params", {})
        tools_desc = self._get_available_tools_desc()

        fix_prompt = f"""你是{self.profile['name']}。刚才你调用了工具但失败了，请修正参数后重试。

原始用户问题: {original_question}

失败的工具调用:
- action: {action}
- params: {json.dumps(params, ensure_ascii=False)}

错误信息: {error_msg[:300]}

可用工具:
{tools_desc}

请分析错误原因，修正参数后返回新的工具调用（JSON格式）:
{{"action": "工具名", "params": {{"参数名": "值"}}}}

注意:
- 如果原参数中的股票代码不是6位数字，请替换为正确的代码
- 如果原参数不适用（如"市场整体"），请改用更合适的工具或参数
- 如果确实无法修正，返回 {{"action": "none", "params": {{}}}}
直接输出 JSON，不要包含任何额外文字。
绝对不要输出 <think> 标签，只输出纯 JSON。"""

        try:
            chunks: list[str] = []
            async for token in self._llm.chat_stream([
                ChatMessage("system", fix_prompt),
                ChatMessage("user", "请修正工具参数并返回 JSON"),
            ]):
                chunks.append(token)
            text = "".join(chunks).strip()

            if not text:
                return None

            # 剥离标签
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            text = re.sub(r"<minimax:.*?</minimax:[^>]+>", "", text, flags=re.DOTALL).strip()
            # 提取 JSON
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            if not text:
                return None

            data = json.loads(text)
            # LLM 可能返回 list 而非 dict，如 [{...}]
            if isinstance(data, list):
                data = data[0] if data else {}
            if not isinstance(data, dict):
                return None
            if data.get("action") == "none":
                return None

            return {
                "engine": failed_tc.get("engine", self.expert_type),
                "action": data.get("action", action),
                "params": data.get("params", params),
            }
        except Exception as e:
            logger.debug(f"_retry_with_fix 解析失败: {e}")
            return None

    async def _execute_tool(self, tc: dict) -> str:
        """执行单个工具调用 — 通过 SkillRegistry 统一分发

        SkillRegistry 自动处理：参数校验、类型转换、错误捕获。
        上下文（data_engine, ensure_snapshot, resolve_code）通过 context dict 注入。
        """
        from engine.expert.skill_registry import SkillRegistry

        action = tc["action"]
        params = tc.get("params", {})

        # 构建执行上下文 — Skill handler 可按需取用
        try:
            from engine.data import get_data_engine
            de = get_data_engine()
        except Exception:
            de = None

        context = {
            "de": de,
            "ensure_snapshot": self._ensure_snapshot,
            "resolve_code": self._resolve_code,
        }

        try:
            return await SkillRegistry.execute(action, params, context=context)
        except Exception as e:
            logger.error(f"工具执行失败 [{action}]: {e}")
            return json.dumps({"error": f"工具调用失败: {e}"}, ensure_ascii=False)

    # ── 旧的 _exec_*_tool 方法已迁移到 engine/expert/skills/ 目录 ──
    # 现在所有工具通过 SkillRegistry 统一注册和执行

    @staticmethod
    def _extract_validation_summary(tool_results: list[str]) -> str:
        """从工具结果中提取数据校验摘要

        扫描每个工具返回的 JSON 中的 _validation 字段，
        汇总所有 warn/error 级别的问题，生成给 LLM 的提示文本。
        """
        issues = []
        for result in tool_results:
            if not result or "_validation" not in result:
                continue
            try:
                data = json.loads(result)
                validation = data.get("_validation", {})
                if not validation or validation.get("status") == "ok":
                    continue
                for issue in validation.get("issues", []):
                    level = issue.get("level", "info")
                    if level in ("warn", "error"):
                        issues.append(f"[{level.upper()}] {issue.get('msg', '')}")
            except (json.JSONDecodeError, Exception):
                continue

        if not issues:
            return ""

        return (
            "\n\n⚠️ 数据质量警告（DataValidator 自动检测到以下问题）:\n"
            + "\n".join(f"  - {i}" for i in issues)
            + "\n请在回复中告知用户这些数据异常，避免基于可能有问题的数据做出错误分析。"
            "如果某个指标数据明显异常，建议用户谨慎参考或换用其他数据源。"
        )

    async def _retry_reply_non_stream(
        self, message: str, tool_results: list[str],
        history: list[dict] | None = None,
        validation_summary: str = "",
    ) -> str:
        """非流式重新生成回复（当流式回复被 think 标签吞掉时的回退方案）

        策略：
        1. 第一次调用 LLM，剥离 think/tool_call 后检查有效内容
        2. 如果有效内容仍然过短（< 200 字），提取 think 中的推理草稿
           + 工具数据，用更强硬的 prompt 做第二次调用
        """
        import re
        from llm.providers import ChatMessage
        from engine.expert.personas import get_current_date_context

        context_parts = []
        if tool_results:
            context_parts.append("工具调用结果：\n" + "\n---\n".join(tool_results))

        system = self.profile["system_prompt"] + f"\n⏰ 当前时间：{get_current_date_context()}"
        system += (
            "\n\n⚠️ 重要：你的所有数据通过工具从数据源实时拉取，"
            "不受模型训练截止日期限制。绝对不要提及「知识截止」「训练数据截止」等字眼。"
            "\n\n🚫🚫🚫 以下规则最高优先级 🚫🚫🚫"
            "\n1. 绝对不要输出任何工具调用！不要输出 [TOOL_CALL]、<tool_call>、function_call、"
            "struct Tool 或任何格式的工具调用代码。"
            "你的工具已在前一步全部执行完毕，数据已在下方提供。"
            "\n2. 直接用 Markdown 格式基于下方已有数据给出详细分析。如果数据不够，就基于已有数据分析，"
            "不要试图调用新的工具或说「正在筛选」「正在获取」。"
            "\n3. 回复必须包含具体的数据分析结论，不能只说「我来扫描」就结束。"
        )
        if not tool_results:
            system += (
                "\n\n📌 当前没有从工具获取到数据（可能你的工具不覆盖此类查询）。"
                "请直接基于你的专业知识回答用户问题，明确说明你能力范围内的分析，"
                "并坦诚指出哪些方面超出了你的工具能力。"
                "绝对不要尝试调用任何工具或输出工具调用格式，直接给出文字分析即可。"
            )
        # ── 注入数据质量警告 ──
        if validation_summary:
            system += validation_summary
        if context_parts:
            system += "\n\n" + "\n\n".join(context_parts)

        messages = [ChatMessage("system", system)]
        for h in (history or []):
            role = "assistant" if h["role"] == "expert" else h["role"]
            content = h.get("content", "")
            messages.append(ChatMessage(role, content))
        messages.append(ChatMessage("user", message))

        result = await self._llm.chat(messages)

        # ── DEBUG: 记录非流式重生成的原始输出 ──
        if _is_llm_debug_raw():
            logger.info(
                f"🔬 [{self.expert_type}] _retry_reply_non_stream 第1次原始输出 "
                f"(长度={len(result)}字):\n{result[:2000]}{'...(截断)' if len(result) > 2000 else ''}"
            )

        # 保存原始结果（用于后续提取 think 草稿）
        raw_result = result

        # 剥离标签
        result = self._strip_llm_tags(result)

        # ── DEBUG: 记录剥离后的内容 ──
        if _is_llm_debug_raw():
            logger.info(
                f"🔬 [{self.expert_type}] _retry_reply_non_stream 第1次剥离后 "
                f"(长度={len(result)}字)"
            )

        # ── 第二次调用：如果剥离后内容仍然过短，说明模型又把有效分析全写在 think 里了 ──
        if len(result.strip()) < 200 and tool_results:
            # 提取 think 中的推理草稿
            think_draft = ""
            think_match = re.search(r"<think>(.*?)</think>", raw_result, re.DOTALL)
            if think_match:
                think_draft = think_match.group(1).strip()

            logger.warning(
                f"⚠️ [{self.expert_type}] 非流式重生成第1次仍然过短({len(result.strip())}字)，"
                f"提取think草稿({len(think_draft)}字)后做第2次调用"
            )

            # 构建更强硬的第二次 prompt：直接把 think 草稿和工具数据都给它
            system2 = self.profile["system_prompt"] + f"\n⏰ 当前时间：{get_current_date_context()}"
            system2 += (
                "\n\n你之前已经完成了数据分析（见下方「分析草稿」），现在请直接把分析结果整理成"
                "用户可以看到的完整 Markdown 报告。"
                "\n\n🚫 绝对禁止输出任何工具调用代码（[TOOL_CALL]、<tool_call> 等）。"
                "你不需要再调用任何工具，所有数据已在下方提供。"
                "\n\n🚫 不要说「正在筛选」「让我调用」之类的话，直接给出分析结论。"
            )
            if think_draft:
                system2 += f"\n\n## 你之前的分析草稿（请基于此整理输出）\n{think_draft}"
            if context_parts:
                system2 += "\n\n" + "\n\n".join(context_parts)

            messages2 = [ChatMessage("system", system2)]
            messages2.append(ChatMessage("user", message))

            result2 = await self._llm.chat(messages2)

            if _is_llm_debug_raw():
                logger.info(
                    f"🔬 [{self.expert_type}] _retry_reply_non_stream 第2次原始输出 "
                    f"(长度={len(result2)}字):\n{result2[:2000]}{'...(截断)' if len(result2) > 2000 else ''}"
                )

            result2 = self._strip_llm_tags(result2)

            if _is_llm_debug_raw():
                logger.info(
                    f"🔬 [{self.expert_type}] _retry_reply_non_stream 第2次剥离后 "
                    f"(长度={len(result2)}字)"
                )

            # 如果第二次比第一次好，用第二次
            if len(result2.strip()) > len(result.strip()):
                result = result2

        return result

    @staticmethod
    def _strip_llm_tags(text: str) -> str:
        """剥离 LLM 输出中的 think / tool_call 等标签，返回纯正文"""
        import re
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        # 未闭合的 <think>（模型输出被截断）
        if "<think>" in text:
            text = text.split("<think>", 1)[0].strip()
        text = re.sub(r"\[TOOL_CALL\].*?\[/TOOL_CALL\]", "", text, flags=re.DOTALL).strip()
        text = re.sub(r"<tool_call>.*?</tool_call>", "", text, flags=re.DOTALL).strip()
        text = re.sub(r"<minimax:tool_call>.*?</minimax:tool_call>", "", text, flags=re.DOTALL).strip()
        # 清理散落的工具调用片段（未闭合的）
        text = re.sub(r"\[TOOL_CALL\].*$", "", text, flags=re.DOTALL).strip()
        text = re.sub(r"<tool_call>.*$", "", text, flags=re.DOTALL).strip()
        text = re.sub(r"\{tool\s*=>.*$", "", text, flags=re.DOTALL).strip()
        return text

    async def _reply_stream(
        self, message: str, tool_results: list[str],
        history: list[dict] | None = None,
        validation_summary: str = "",
    ) -> AsyncGenerator[tuple[str, str], None]:
        """流式生成回复（自动过滤 <think> / <minimax:*> 标签内容）"""
        from llm.providers import ChatMessage
        from engine.expert.personas import get_current_date_context

        context_parts = []
        if tool_results:
            context_parts.append("工具调用结果：\n" + "\n---\n".join(tool_results))

        system = self.profile["system_prompt"] + f"\n⏰ 当前时间：{get_current_date_context()}"
        system += (
            "\n\n⚠️ 重要：你的所有数据通过工具从数据源实时拉取，"
            "不受模型训练截止日期限制。绝对不要提及「知识截止」「训练数据截止」等字眼。"
            "\n\n🚫🚫🚫 以下规则最高优先级 🚫🚫🚫"
            "\n1. 绝对不要在回复正文中输出任何工具调用！包括 [TOOL_CALL]、<tool_call>、"
            "function_call、struct Tool 或任何格式的工具调用代码。"
            "你的工具已在前一步自动执行完毕，结果已包含在上下文中。"
            "\n2. 直接基于下方已有数据进行分析和回答。如果数据不够也要基于已有数据给出结论，"
            "不要说「正在筛选」「正在获取」「让我查一下」就结束。"
            "\n3. 回复必须包含具体的数据分析结论、明确的看法和具体标的推荐（如果数据支持）。"
        )
        if not tool_results:
            system += (
                "\n\n📌 当前没有从工具获取到数据（可能你的工具不覆盖此类查询）。"
                "请直接基于你的专业知识回答用户问题，明确说明你能力范围内的分析，"
                "并坦诚指出哪些方面超出了你的工具能力。"
                "绝对不要尝试调用任何工具或输出工具调用格式，直接给出文字分析即可。"
            )
        # ── 注入数据质量警告 ──
        if validation_summary:
            system += validation_summary
        if context_parts:
            system += "\n\n" + "\n\n".join(context_parts)

        # 构建消息列表（含对话历史）
        messages = [ChatMessage("system", system)]
        for h in (history or []):
            role = "assistant" if h["role"] == "expert" else h["role"]
            content = h.get("content", "")
            messages.append(ChatMessage(role, content))
        messages.append(ChatMessage("user", message))

        accumulated = ""
        in_skip = False          # 跳过区域
        skip_end_tag = ""        # 当前跳过区域的结束标签
        raw_buffer = ""

        # ── DEBUG: 收集完整原始输出和被 skip 的内容 ──
        _debug_raw_all = []       # LLM 原始输出（所有 token 拼接）
        _debug_skipped_parts = [] # 被 skip 标签过滤掉的内容
        _debug_current_skip = []  # 当前正在 skip 的内容

        # 需要过滤的标签及其结束标签（包括 XML 尖括号和方括号格式）
        SKIP_TAGS = {
            "<think>": "</think>",
            "<minimax:tool_call>": "</minimax:tool_call>",
            "<minimax:search_result>": "</minimax:search_result>",
            "<tool_call>": "</tool_call>",
            "<tool_code>": "</tool_code>",
            "[TOOL_CALL]": "[/TOOL_CALL]",
            "[tool_call]": "[/tool_call]",
        }

        try:
            skip_bytes = 0  # skip 区域累积字节数

            async for token in self._llm.chat_stream(messages):
                raw_buffer += token

                # ── DEBUG: 收集原始 token ──
                if LLM_DEBUG_RAW:
                    _debug_raw_all.append(token)

                # 检测进入跳过区域
                if not in_skip:
                    for start_tag, end_tag in SKIP_TAGS.items():
                        if start_tag in raw_buffer:
                            before = raw_buffer.split(start_tag, 1)[0]
                            if before:
                                accumulated += before
                                yield before, accumulated
                            in_skip = True
                            skip_end_tag = end_tag
                            skip_bytes = 0
                            raw_buffer = raw_buffer.split(start_tag, 1)[1]
                            # ── DEBUG: 记录 skip 区域开始 ──
                            if LLM_DEBUG_RAW:
                                _debug_current_skip = [f"{start_tag}", raw_buffer]
                            break
                    if in_skip:
                        continue

                # 检测离开跳过区域
                if in_skip and skip_end_tag in raw_buffer:
                    # ── DEBUG: 记录 skip 区域结束 ──
                    if LLM_DEBUG_RAW:
                        _debug_current_skip.append(skip_end_tag)
                        _debug_skipped_parts.append("".join(_debug_current_skip))
                        _debug_current_skip = []
                    in_skip = False
                    remaining = raw_buffer.split(skip_end_tag, 1)[1]
                    raw_buffer = remaining.lstrip("\n")
                    skip_end_tag = ""
                    skip_bytes = 0
                    continue

                # 在跳过块内：丢弃内容，但防止缓冲区无限增长
                if in_skip:
                    # ── DEBUG: 收集被 skip 的内容 ──
                    if LLM_DEBUG_RAW:
                        _debug_current_skip.append(token)
                    skip_bytes += len(token)
                    # 保护：如果 skip 区域累积超过 20000 字节还未关闭，强制退出
                    # （MiniMax-M2.5 的 <think> 内容通常在 5000~15000 字节）
                    if skip_bytes > 20000:
                        logger.warning(f"skip 区域未关闭(>{skip_bytes}B)，强制退出: {skip_end_tag}")
                        # ── DEBUG: 记录未关闭的 skip ──
                        if LLM_DEBUG_RAW:
                            _debug_current_skip.append(f"[FORCE_EXIT>{skip_bytes}B]")
                            _debug_skipped_parts.append("".join(_debug_current_skip))
                            _debug_current_skip = []
                        in_skip = False
                        raw_buffer = ""
                        skip_end_tag = ""
                        skip_bytes = 0
                    elif len(raw_buffer) > 200:
                        raw_buffer = raw_buffer[-50:]
                    continue

                # 正常正文：检查是否可能是不完整的标签（< 或 [ 开头）
                if (("<" in raw_buffer and not raw_buffer.endswith(">")) or
                        ("[" in raw_buffer and raw_buffer.rstrip().endswith("]") is False and "[TOOL" in raw_buffer.upper())):
                    if len(raw_buffer) < 30:
                        continue

                # 推送正文 token
                if raw_buffer:
                    accumulated += raw_buffer
                    yield raw_buffer, accumulated
                    raw_buffer = ""

            # 处理残余缓冲区
            if raw_buffer and not in_skip:
                accumulated += raw_buffer
                yield raw_buffer, accumulated
            # ── DEBUG: 如果流结束时还在 skip 中，记录未关闭的部分 ──
            elif in_skip and LLM_DEBUG_RAW:
                _debug_current_skip.append("[STREAM_END_IN_SKIP]")
                _debug_skipped_parts.append("".join(_debug_current_skip))

        except Exception as e:
            logger.error(f"reply_stream 失败: {e}")
            yield f"回复生成失败: {e}", f"回复生成失败: {e}"
        finally:
            # ── DEBUG: 打印完整的 LLM 原始输出诊断日志 ──
            if LLM_DEBUG_RAW:
                raw_full = "".join(_debug_raw_all)
                logger.info(
                    f"\n{'='*60}\n"
                    f"🔬 [{self.expert_type}] LLM 原始输出 DEBUG\n"
                    f"{'='*60}\n"
                    f"📏 原始总长度: {len(raw_full)} 字符\n"
                    f"📝 保留内容长度: {len(accumulated)} 字符\n"
                    f"🗑️ 被过滤块数: {len(_debug_skipped_parts)}\n"
                    f"{'─'*60}\n"
                    f"📤 LLM 完整原始输出:\n{raw_full}\n"
                    f"{'─'*60}\n"
                    f"✅ 保留给用户的内容:\n{accumulated}\n"
                    f"{'─'*60}"
                )
                for i, sp in enumerate(_debug_skipped_parts):
                    logger.info(
                        f"🗑️ [{self.expert_type}] 被过滤块[{i}] "
                        f"(长度={len(sp)}字): {sp[:1000]}{'...(截断)' if len(sp) > 1000 else ''}"
                    )

    def _get_available_tools_desc(self) -> str:
        """获取当前引擎可用工具的描述 — 由 SkillRegistry 自动生成"""
        from engine.expert.skill_registry import SkillRegistry
        return SkillRegistry.get_tools_desc(self.expert_type)


def get_expert_profiles() -> list[dict]:
    """返回所有专家的配置信息（用于前端展示）"""
    return [
        {
            "type": k,
            "name": v["name"],
            "icon": v["icon"],
            "color": v["color"],
            "description": v["description"],
            "suggestions": v["suggestions"],
        }
        for k, v in EXPERT_PROFILES.items()
    ]
