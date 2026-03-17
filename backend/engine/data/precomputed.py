"""
公司概况加载器

从 data/precomputed/company_profiles.json 加载公司基础信息。
兼容 v2.0 的 industry_mapping.json 格式。
"""

import json
from pathlib import Path
from loguru import logger

from config import PROJECT_ROOT, DATA_DIR
PRECOMPUTED_DIR = DATA_DIR / "precomputed"


def load_profiles() -> dict[str, dict]:
    """
    加载公司概况 {code: {name, industry, scope, ...}}

    优先加载 company_profiles.json，兼容 v2.0 的 industry_mapping.json。
    """
    profiles: dict[str, dict] = {}
    profiles_path = PRECOMPUTED_DIR / "company_profiles.json"

    if profiles_path.exists():
        try:
            with open(profiles_path, "r", encoding="utf-8") as f:
                profiles = json.load(f)
            logger.info(f"📋 公司概况加载: {len(profiles)} 只股票")
            return profiles
        except Exception as e:
            logger.warning(f"公司概况加载失败: {e}")

    # 兼容 v2.0 的 industry_mapping.json
    industry_path = PRECOMPUTED_DIR / "industry_mapping.json"
    if industry_path.exists():
        try:
            with open(industry_path, "r", encoding="utf-8") as f:
                industry_mapping = json.load(f)
            for code, info in industry_mapping.items():
                profiles[code] = {
                    "code": code,
                    "industry": info.get("industry_name", ""),
                }
            logger.info(f"📋 兼容 v2.0 行业映射: {len(profiles)} 只")
        except Exception:
            pass

    return profiles
