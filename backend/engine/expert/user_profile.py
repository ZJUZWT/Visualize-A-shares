"""用户偏好追踪器 — 借鉴 OpenClaw USER 层用户记忆

从对话中提取用户投资偏好（风险偏好、关注板块、交易风格），
跨 session 累积，注入 system prompt 实现个性化回复。
"""

from __future__ import annotations

import json
import re
from datetime import datetime

import duckdb
from loguru import logger


# 风险偏好关键词
_RISK_PATTERNS = {
    "aggressive": [r"激进", r"高风险", r"能承受.*亏", r"赌", r"大仓位", r"全仓"],
    "conservative": [r"保守", r"稳健", r"不能亏", r"低风险", r"安全", r"少亏"],
    "moderate": [r"适中", r"平衡", r"中等风险"],
}

# 板块关键词
_SECTOR_KEYWORDS = [
    "新能源", "半导体", "芯片", "光伏", "储能", "锂电", "白酒", "医药",
    "军工", "汽车", "消费", "银行", "地产", "科技", "AI", "机器人",
    "传媒", "游戏", "教育", "农业", "化工", "有色", "煤炭", "石油",
]

# 交易风格关键词
_STYLE_PATTERNS = {
    "短线": [r"短线", r"快进快出", r"打板", r"追涨", r"T\+0", r"日内"],
    "波段": [r"波段", r"中线", r"一两周", r"几周"],
    "长线": [r"长线", r"长期", r"价值投资", r"持有.*年", r"定投"],
}


def extract_preferences(message: str) -> dict:
    """从用户消息中提取投资偏好（关键词规则，不调 LLM）

    Returns: {"risk": "...", "sectors": [...], "style": "..."} — 只含检测到的字段
    """
    prefs: dict = {}

    # 风险偏好
    for risk_level, patterns in _RISK_PATTERNS.items():
        if any(re.search(p, message) for p in patterns):
            prefs["risk"] = risk_level
            break

    # 关注板块
    sectors = [s for s in _SECTOR_KEYWORDS if s in message]
    if sectors:
        prefs["sectors"] = sectors

    # 交易风格
    for style, patterns in _STYLE_PATTERNS.items():
        if any(re.search(p, message) for p in patterns):
            prefs["style"] = style
            break

    return prefs


class UserProfileTracker:
    """用户偏好持久化追踪器"""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._init_table()

    def _get_db(self):
        return duckdb.connect(self._db_path)

    def _init_table(self):
        con = None
        try:
            con = self._get_db()
            con.execute("CREATE SCHEMA IF NOT EXISTS expert")
            con.execute("""
                CREATE TABLE IF NOT EXISTS expert.user_profiles (
                    profile_id VARCHAR PRIMARY KEY,
                    preferences JSON NOT NULL DEFAULT '{}',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        except Exception as e:
            logger.warning(f"user_profiles 表初始化失败: {e}")
        finally:
            if con:
                con.close()

    def get(self, profile_id: str = "global") -> dict:
        """获取用户偏好"""
        con = None
        try:
            con = self._get_db()
            row = con.execute(
                "SELECT preferences FROM expert.user_profiles WHERE profile_id = ?",
                [profile_id],
            ).fetchone()
            if row:
                return json.loads(row[0]) if isinstance(row[0], str) else row[0]
            return {}
        except Exception as e:
            logger.debug(f"获取用户偏好失败: {e}")
            return {}
        finally:
            if con:
                con.close()

    def update(self, profile_id: str, new_prefs: dict) -> None:
        """合并更新用户偏好（sectors 合并，其他字段覆盖）"""
        if not new_prefs:
            return
        existing = self.get(profile_id)

        # 合并 sectors（去重）
        if "sectors" in new_prefs:
            old_sectors = set(existing.get("sectors", []))
            old_sectors.update(new_prefs["sectors"])
            existing["sectors"] = sorted(old_sectors)

        # 其他字段直接覆盖
        for key in ("risk", "style"):
            if key in new_prefs:
                existing[key] = new_prefs[key]

        con = None
        try:
            con = self._get_db()
            prefs_json = json.dumps(existing, ensure_ascii=False)
            con.execute("""
                INSERT INTO expert.user_profiles (profile_id, preferences, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT (profile_id) DO UPDATE SET
                    preferences = EXCLUDED.preferences,
                    updated_at = EXCLUDED.updated_at
            """, [profile_id, prefs_json, datetime.now()])
        except Exception as e:
            logger.warning(f"更新用户偏好失败: {e}")
        finally:
            if con:
                con.close()

    def format_profile_prompt(self, profile_id: str = "global") -> str:
        """格式化用户画像，供注入 system prompt"""
        prefs = self.get(profile_id)
        if not prefs:
            return ""

        lines = ["## 用户投资偏好（请据此个性化回复）"]

        risk = prefs.get("risk")
        if risk:
            risk_labels = {
                "aggressive": "激进型 — 能承受较大亏损，追求高收益",
                "conservative": "保守型 — 厌恶亏损，偏好稳健策略",
                "moderate": "均衡型 — 追求风险收益平衡",
            }
            lines.append(f"- 风险偏好: {risk_labels.get(risk, risk)}")

        sectors = prefs.get("sectors")
        if sectors:
            lines.append(f"- 关注板块: {', '.join(sectors)}")

        style = prefs.get("style")
        if style:
            lines.append(f"- 交易风格: {style}")

        return "\n".join(lines)
