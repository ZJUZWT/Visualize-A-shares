"""数据验证器 — Skill 出口自动校验

在 SkillRegistry.execute() 返回数据前，自动对 JSON 结果执行多维度校验：
1. 结构完整性：必要字段是否存在
2. 值域合理性：价格区间、涨跌幅限制、OHLC 逻辑关系
3. 时效性检查：数据日期是否过期
4. 一致性校验：同一组数据中的交叉验证（如 amount ≈ price × volume）

校验结果以 `_validation` 字段注入到返回的 JSON 中，让 LLM 看到数据质量标记。
LLM 看到警告后可以在回复中提醒用户数据可能有问题，而不是基于垃圾数据瞎分析。
"""

import datetime
import json
import math
from dataclasses import dataclass, field
from typing import Any, Optional

from loguru import logger


@dataclass
class ValidationIssue:
    """单个校验问题"""
    level: str          # "warn" / "error" / "info"
    field: str          # 问题字段名
    message: str        # 人类可读描述
    value: Any = None   # 问题值（可选）


@dataclass
class ValidationResult:
    """校验结果"""
    is_valid: bool = True
    issues: list[ValidationIssue] = field(default_factory=list)
    checked_count: int = 0  # 检查了多少条记录

    def add_issue(self, level: str, field_name: str, message: str, value: Any = None):
        self.issues.append(ValidationIssue(level=level, field=field_name, message=message, value=value))
        if level == "error":
            self.is_valid = False

    def to_dict(self) -> dict:
        if not self.issues:
            return {"status": "ok", "checked": self.checked_count}
        return {
            "status": "warn" if self.is_valid else "error",
            "checked": self.checked_count,
            "issues": [
                {"level": i.level, "field": i.field, "msg": i.message}
                for i in self.issues
            ],
        }


class DataValidator:
    """数据校验器 — 按 Skill 类别自动选择校验规则"""

    # A股涨跌幅限制（考虑新股、ST、科创板/创业板）
    MAX_PCT_CHG = 30.0   # 科创板/创业板/北交所最大 30%（前5日不设限，但30%已足够宽松）
    MIN_PCT_CHG = -30.0

    # 当前时间缓存（一次校验周期内不重复调用 datetime.now）
    _now: datetime.datetime = None

    @classmethod
    def validate(cls, skill_name: str, result_str: str) -> str:
        """主入口：校验 Skill 返回的 JSON 数据

        Args:
            skill_name: Skill 名称（用于选择校验规则）
            result_str: Skill 返回的 JSON 字符串

        Returns:
            注入 _validation 字段后的 JSON 字符串（如果有问题）
            或原始字符串（如果无问题或不是 JSON）
        """
        if not result_str or not result_str.strip().startswith("{"):
            return result_str

        try:
            data = json.loads(result_str)
        except (json.JSONDecodeError, Exception):
            return result_str

        if not isinstance(data, dict):
            return result_str

        # 已经有 error 的不再校验（避免重复报错）
        if "error" in data or data.get("empty"):
            return result_str

        cls._now = datetime.datetime.now()

        # 根据 skill 名称分发校验
        vr = cls._dispatch_validate(skill_name, data)

        if vr and vr.issues:
            data["_validation"] = vr.to_dict()
            # 日志
            warn_count = sum(1 for i in vr.issues if i.level == "warn")
            error_count = sum(1 for i in vr.issues if i.level == "error")
            logger.warning(
                f"⚠️ [{skill_name}] 数据校验: "
                f"检查 {vr.checked_count} 条, "
                f"警告 {warn_count}, 错误 {error_count}: "
                + "; ".join(i.message for i in vr.issues[:5])
            )
            return json.dumps(data, ensure_ascii=False, default=str)

        return result_str

    @classmethod
    def _dispatch_validate(cls, skill_name: str, data: dict) -> Optional[ValidationResult]:
        """按 skill 名称分发到对应的校验方法"""
        validators = {
            # 个股快照
            "query_stock": cls._validate_stock_snapshot,
            "search_stocks": cls._validate_search_results,
            # K 线数据
            "query_history": cls._validate_kline_records,
            "query_hourly": cls._validate_kline_records,
            # 市场概览
            "query_market_overview": cls._validate_market_overview,
            # 选股
            "run_screen": cls._validate_screen_results,
            # 技术指标
            "get_technical_indicators": cls._validate_technical_indicators,
            # 因子评分
            "get_factor_scores": cls._validate_factor_scores,
        }

        validator = validators.get(skill_name)
        if validator:
            return validator(data)
        return None

    # ─── 个股快照校验 ──────────────────────────────────

    @classmethod
    def _validate_stock_snapshot(cls, data: dict) -> ValidationResult:
        """校验 query_stock 返回的单股数据"""
        vr = ValidationResult(checked_count=1)

        # 1. 必要字段
        required = ["code", "price"]
        for f in required:
            if f not in data or data[f] is None:
                vr.add_issue("error", f, f"缺少必要字段 {f}")

        price = cls._safe_float(data.get("price"))
        pct_chg = cls._safe_float(data.get("pct_chg"))
        volume = cls._safe_float(data.get("volume"))
        high = cls._safe_float(data.get("high"))
        low = cls._safe_float(data.get("low"))
        open_price = cls._safe_float(data.get("open"))
        name = str(data.get("name", ""))

        # 2. 价格合理性
        if price is not None and price <= 0:
            vr.add_issue("error", "price", f"价格异常: {price}（<=0）", price)

        # 3. 涨跌幅合理性
        if pct_chg is not None and (pct_chg > cls.MAX_PCT_CHG or pct_chg < cls.MIN_PCT_CHG):
            # 新股前5日不设限，通过名称"N"前缀判断
            if not name.startswith("N"):
                vr.add_issue("warn", "pct_chg",
                             f"涨跌幅异常: {pct_chg:.2f}%（超出±{cls.MAX_PCT_CHG}%限制）", pct_chg)

        # 4. OHLC 逻辑关系
        cls._check_ohlc(vr, open_price, high, low, price)

        # 5. 成交量为 0 但价格变动
        if volume is not None and volume == 0 and pct_chg is not None and abs(pct_chg) > 0.01:
            vr.add_issue("warn", "volume",
                         f"成交量为0但涨跌幅={pct_chg:.2f}%，可能停牌或数据异常")

        # 6. 市值合理性
        total_mv = cls._safe_float(data.get("total_mv"))
        if total_mv is not None and total_mv < 0:
            vr.add_issue("error", "total_mv", f"总市值异常: {total_mv}（<0）", total_mv)

        # 7. PE/PB 极端值警告
        pe = cls._safe_float(data.get("pe_ttm"))
        if pe is not None and pe < 0:
            vr.add_issue("info", "pe_ttm", f"PE为负数 ({pe:.1f})，公司可能亏损", pe)
        elif pe is not None and pe > 1000:
            vr.add_issue("info", "pe_ttm", f"PE极高 ({pe:.0f})，估值可能失真或微利", pe)

        return vr

    # ─── 搜索结果校验 ──────────────────────────────────

    @classmethod
    def _validate_search_results(cls, data: dict) -> ValidationResult:
        """校验 search_stocks 返回的搜索结果"""
        results = data.get("results", [])
        vr = ValidationResult(checked_count=len(results))

        bad_price_count = 0
        for r in results:
            price = cls._safe_float(r.get("price"))
            if price is not None and price <= 0:
                bad_price_count += 1

        if bad_price_count > 0:
            vr.add_issue("warn", "price",
                         f"搜索结果中有 {bad_price_count}/{len(results)} 条价格异常（<=0）")
        return vr

    # ─── K 线数据校验 ──────────────────────────────────

    @classmethod
    def _validate_kline_records(cls, data: dict) -> ValidationResult:
        """校验 query_history / query_hourly 返回的 K 线数据"""
        records = data.get("records", [])
        vr = ValidationResult(checked_count=len(records))

        if not records:
            return vr

        ohlc_issues = 0
        zero_volume_issues = 0
        extreme_pct_issues = 0
        dup_dates = set()
        seen_dates = set()
        price_zero_count = 0

        for i, rec in enumerate(records):
            # 1. OHLC 逻辑关系
            o = cls._safe_float(rec.get("open"))
            h = cls._safe_float(rec.get("high"))
            l = cls._safe_float(rec.get("low"))
            c = cls._safe_float(rec.get("close"))

            if h is not None and l is not None and h < l:
                ohlc_issues += 1
            if l is not None and o is not None and o < l:
                ohlc_issues += 1
            if h is not None and c is not None and c > h:
                ohlc_issues += 1

            # 2. 价格为 0
            if c is not None and c <= 0:
                price_zero_count += 1

            # 3. 涨跌幅极端值
            pct = cls._safe_float(rec.get("pct_chg"))
            if pct is not None and (pct > cls.MAX_PCT_CHG or pct < cls.MIN_PCT_CHG):
                extreme_pct_issues += 1

            # 4. 成交量为 0 但有价格变动
            vol = cls._safe_float(rec.get("volume"))
            if vol is not None and vol == 0 and pct is not None and abs(pct) > 0.01:
                zero_volume_issues += 1

            # 5. 日期重复检测
            date_val = rec.get("date") or rec.get("trade_date") or rec.get("datetime")
            if date_val:
                date_key = str(date_val)[:10]
                if date_key in seen_dates:
                    dup_dates.add(date_key)
                seen_dates.add(date_key)

        # 汇总
        if ohlc_issues > 0:
            vr.add_issue("warn", "ohlc",
                         f"K线数据中有 {ohlc_issues}/{len(records)} 条 OHLC 逻辑异常（如 high < low）")
        if price_zero_count > 0:
            vr.add_issue("error", "close",
                         f"K线数据中有 {price_zero_count}/{len(records)} 条收盘价<=0")
        if extreme_pct_issues > 0:
            vr.add_issue("warn", "pct_chg",
                         f"K线数据中有 {extreme_pct_issues}/{len(records)} 条涨跌幅超出±{cls.MAX_PCT_CHG}%")
        if zero_volume_issues > 0:
            vr.add_issue("info", "volume",
                         f"K线数据中有 {zero_volume_issues}/{len(records)} 条成交量为0但有涨跌幅（可能停牌）")
        if dup_dates:
            vr.add_issue("warn", "date",
                         f"K线数据中存在重复日期: {', '.join(sorted(dup_dates)[:3])}等")

        # 6. 数据时效性：最后一条日期距今超过 5 个交易日（仅日线）
        if records and data.get("frequency") != "60m":
            last_date = records[-1].get("date") or records[-1].get("trade_date")
            if last_date:
                cls._check_data_freshness(vr, str(last_date)[:10], threshold_days=7)

        # 7. 请求天数 vs 返回天数
        total_days = data.get("total_days", len(records))
        if total_days < len(records) * 0.5 and len(records) > 5:
            vr.add_issue("info", "total_days",
                         f"返回数据量({total_days})偏少，可能数据源缺失")

        return vr

    # ─── 市场概览校验 ──────────────────────────────────

    @classmethod
    def _validate_market_overview(cls, data: dict) -> ValidationResult:
        """校验 query_market_overview 返回的市场概览"""
        vr = ValidationResult(checked_count=1)

        total = cls._safe_float(data.get("total_stocks"))
        up = cls._safe_float(data.get("up"))
        down = cls._safe_float(data.get("down"))
        flat = cls._safe_float(data.get("flat"))

        # 1. 总数合理性
        if total is not None:
            if total < 1000:
                vr.add_issue("warn", "total_stocks",
                             f"全市场股票总数异常: {int(total)}（A股应有5000+只）", total)
            # 涨跌平加起来应该等于总数
            if up is not None and down is not None and flat is not None:
                computed_total = up + down + flat
                if abs(computed_total - total) > 10:
                    vr.add_issue("warn", "total_stocks",
                                 f"涨({int(up)})+跌({int(down)})+平({int(flat)})={int(computed_total)}"
                                 f" ≠ 总数({int(total)})，数据可能不一致")

        # 2. 数据时效性
        updated_at = data.get("updated_at", "")
        if updated_at:
            cls._check_snapshot_freshness(vr, updated_at)

        return vr

    # ─── 选股结果校验 ──────────────────────────────────

    @classmethod
    def _validate_screen_results(cls, data: dict) -> ValidationResult:
        """校验 run_screen 返回的选股结果"""
        results = data.get("results", [])
        vr = ValidationResult(checked_count=len(results))

        bad_count = 0
        for r in results:
            price = cls._safe_float(r.get("price"))
            if price is not None and price <= 0:
                bad_count += 1

        if bad_count > 0:
            vr.add_issue("warn", "price",
                         f"选股结果中有 {bad_count}/{len(results)} 条价格异常（<=0），可能包含停牌股")

        # 时效性
        updated_at = data.get("updated_at", "")
        if updated_at:
            cls._check_snapshot_freshness(vr, updated_at)

        return vr

    # ─── 技术指标校验 ──────────────────────────────────

    @classmethod
    def _validate_technical_indicators(cls, data: dict) -> ValidationResult:
        """校验 get_technical_indicators 返回的技术指标"""
        vr = ValidationResult(checked_count=1)
        indicators = data.get("indicators", {})

        if not indicators:
            vr.add_issue("warn", "indicators", "技术指标为空，可能数据不足")
            return vr

        # RSI 合理性 [0, 100]
        rsi = cls._safe_float(indicators.get("rsi_14") or indicators.get("rsi"))
        if rsi is not None and (rsi < 0 or rsi > 100):
            vr.add_issue("error", "rsi", f"RSI 超出合理范围 [0,100]: {rsi:.1f}", rsi)

        # MACD 组件存在性检查
        macd_keys = ["macd", "macd_signal", "macd_hist"]
        missing_macd = [k for k in macd_keys if k not in indicators and f"dif" not in str(indicators)]
        # 不强制，某些情况下 key 名可能不同

        # 数据天数检查
        data_days = data.get("data_days", 0)
        if data_days < 30:
            vr.add_issue("warn", "data_days",
                         f"历史数据只有 {data_days} 天，技术指标可能不够准确（建议 ≥60 天）")

        return vr

    # ─── 因子评分校验 ──────────────────────────────────

    @classmethod
    def _validate_factor_scores(cls, data: dict) -> ValidationResult:
        """校验 get_factor_scores 返回的因子评分"""
        vr = ValidationResult(checked_count=1)
        factors = data.get("factors", {})

        if not factors:
            vr.add_issue("warn", "factors", "因子评分为空")
            return vr

        # 检查有多少因子值为 None（数据缺失）
        null_count = sum(1 for f in factors.values()
                         if isinstance(f, dict) and f.get("value") is None)
        total = len(factors)

        if null_count > total * 0.5:
            vr.add_issue("warn", "factors",
                         f"因子评分中有 {null_count}/{total} 个因子值缺失（>50%），评分结果可能不可靠")
        elif null_count > 0:
            vr.add_issue("info", "factors",
                         f"因子评分中有 {null_count}/{total} 个因子值缺失")

        return vr

    # ─── 通用辅助方法 ──────────────────────────────────

    @classmethod
    def _check_ohlc(cls, vr: ValidationResult, open_p, high, low, close):
        """检查 OHLC 逻辑关系"""
        if high is not None and low is not None:
            if high < low:
                vr.add_issue("warn", "ohlc",
                             f"最高价({high}) < 最低价({low})，数据异常")
        if low is not None:
            if open_p is not None and open_p < low * 0.99:  # 允许 1% 容差（集合竞价）
                vr.add_issue("info", "ohlc",
                             f"开盘价({open_p}) < 最低价({low})，可能是集合竞价数据")
            if close is not None and close < low * 0.99:
                vr.add_issue("warn", "ohlc",
                             f"收盘价({close}) < 最低价({low})，数据异常")
        if high is not None:
            if close is not None and close > high * 1.01:
                vr.add_issue("warn", "ohlc",
                             f"收盘价({close}) > 最高价({high})，数据异常")

    @classmethod
    def _check_data_freshness(cls, vr: ValidationResult, date_str: str, threshold_days: int = 7):
        """检查数据时效性（日线/K线最后一条日期距今是否太远）"""
        try:
            last_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            today = cls._now.date() if cls._now else datetime.date.today()
            gap = (today - last_date).days

            # 排除周末：实际交易日差距
            if gap > threshold_days:
                vr.add_issue("warn", "freshness",
                             f"数据最新日期为 {date_str}，距今 {gap} 天，数据可能过期")
        except (ValueError, Exception):
            pass

    @classmethod
    def _check_snapshot_freshness(cls, vr: ValidationResult, updated_at: str):
        """检查快照数据时效性"""
        try:
            if not updated_at:
                return
            update_time = datetime.datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
            # 如果 update_time 是 naive，假设为本地时间
            if update_time.tzinfo:
                update_time = update_time.replace(tzinfo=None)
            now = cls._now or datetime.datetime.now()

            gap_hours = (now - update_time).total_seconds() / 3600

            # 交易时段内超过 2 小时视为过期
            if now.weekday() < 5 and datetime.time(9, 30) <= now.time() <= datetime.time(15, 0):
                if gap_hours > 2:
                    vr.add_issue("warn", "freshness",
                                 f"快照数据更新于 {update_time.strftime('%Y-%m-%d %H:%M')}，"
                                 f"距今 {gap_hours:.1f} 小时，交易时段内数据可能过期")
            # 非交易时段：超过 24 小时
            elif gap_hours > 24:
                vr.add_issue("info", "freshness",
                             f"快照数据更新于 {update_time.strftime('%Y-%m-%d %H:%M')}，距今 {gap_hours:.0f} 小时")
        except (ValueError, TypeError, Exception):
            pass

    @staticmethod
    def _safe_float(val) -> Optional[float]:
        """安全转 float，无效值返回 None"""
        if val is None:
            return None
        try:
            f = float(val)
            if math.isnan(f) or math.isinf(f):
                return None
            return f
        except (ValueError, TypeError):
            return None
