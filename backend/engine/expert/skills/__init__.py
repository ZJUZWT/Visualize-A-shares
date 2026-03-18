"""Skills 包 — 所有 Skill 定义

import 此包即触发所有子模块中的 @SkillRegistry.register 装饰器。
新增 Skill 只需：
1. 在此目录新建 xxx_skills.py
2. 在本文件加一行 import
"""

from engine.expert.skills import data_skills      # noqa: F401
from engine.expert.skills import quant_skills     # noqa: F401
from engine.expert.skills import info_skills      # noqa: F401
from engine.expert.skills import industry_skills  # noqa: F401
