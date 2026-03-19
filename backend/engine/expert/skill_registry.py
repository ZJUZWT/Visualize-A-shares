"""Skill 注册表 — 工具的声明式注册与动态发现

每个 Skill 是一个自描述的工具：
- 声明参数 schema、所属专家、分类
- 通过 @skill 装饰器自动注册
- SkillRegistry 提供统一的发现、描述生成、执行入口

这样新增工具只需写一个函数 + 一行装饰器，不需要改 3 个文件。
"""

import asyncio
import inspect
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from loguru import logger


@dataclass
class SkillParam:
    """Skill 参数定义"""
    name: str
    type: str           # "str", "int", "float", "dict", "bool"
    description: str = ""
    required: bool = True
    default: Any = None


@dataclass
class Skill:
    """一个可被 LLM 调用的技能/工具"""
    name: str                      # 工具名（LLM 看到的 action 名）
    description: str               # 给 LLM 看的一句话描述
    handler: Callable              # 实际执行函数（sync 或 async）
    expert_types: List[str]        # 哪些专家可以用（如 ["data", "quant"]）
    params: List[SkillParam] = field(default_factory=list)
    category: str = "general"      # 分类标签（用于分组展示）
    version: str = "1.0"           # 版本号（便于后续升级）


class SkillRegistry:
    """全局 Skill 注册表 — 单例"""

    _skills: Dict[str, Skill] = {}
    _initialized: bool = False

    # ─── 注册 ───────────────────────────────────────────

    @classmethod
    def register(
        cls,
        name: str,
        description: str,
        expert_types: List[str],
        params: Optional[List[dict]] = None,
        category: str = "general",
        version: str = "1.0",
    ):
        """装饰器：注册一个 Skill

        用法：
            @SkillRegistry.register(
                name="query_stock",
                description="查询单只股票的全维度详情",
                expert_types=["data"],
                params=[{"name": "code", "type": "str", "description": "股票代码或名称"}],
                category="stock",
            )
            async def query_stock(code: str, **ctx):
                ...
        """
        param_objs = []
        for p in (params or []):
            param_objs.append(SkillParam(
                name=p["name"],
                type=p.get("type", "str"),
                description=p.get("description", ""),
                required=p.get("required", True),
                default=p.get("default"),
            ))

        def decorator(func: Callable) -> Callable:
            skill = Skill(
                name=name,
                description=description,
                handler=func,
                expert_types=expert_types,
                params=param_objs,
                category=category,
                version=version,
            )
            cls._skills[name] = skill
            return func

        return decorator

    # ─── 发现 ───────────────────────────────────────────

    @classmethod
    def get_skills_for_expert(cls, expert_type: str) -> List[Skill]:
        """获取某个专家类型可用的所有 Skill"""
        cls._ensure_loaded()
        return [s for s in cls._skills.values() if expert_type in s.expert_types]

    @classmethod
    def get_skill(cls, name: str) -> Optional[Skill]:
        """按名称获取 Skill"""
        cls._ensure_loaded()
        return cls._skills.get(name)

    @classmethod
    def get_all_skills(cls) -> Dict[str, Skill]:
        """获取所有已注册的 Skill"""
        cls._ensure_loaded()
        return dict(cls._skills)

    # ─── 工具描述生成（给 LLM 看的） ─────────────────────

    @classmethod
    def get_tools_desc(cls, expert_type: str) -> str:
        """自动生成给 LLM 的工具描述文本

        输出格式和原来的 TOOLS_DESC 完全一致，确保 LLM 兼容：
            - tool_name(param1: type, param2: type): 描述
        """
        cls._ensure_loaded()
        skills = cls.get_skills_for_expert(expert_type)
        if not skills:
            return "无可用工具"

        lines = []
        for skill in skills:
            if skill.params:
                param_str = ", ".join(
                    f"{p.name}: {p.type}" for p in skill.params
                )
                lines.append(f"- {skill.name}({param_str}): {skill.description}")
            else:
                lines.append(f"- {skill.name}(): {skill.description}")
        return "\n".join(lines)

    # ─── OpenAI tools schema 生成（原生 Function Calling 用） ──

    # SkillParam.type → JSON Schema type 映射
    _TYPE_MAP: dict[str, str] = {
        "str": "string",
        "int": "integer",
        "float": "number",
        "bool": "boolean",
        "dict": "object",
    }

    @classmethod
    def get_tools_schema(cls, expert_type: str) -> list[dict]:
        """生成 OpenAI 兼容的 tools JSON（用于原生 Function Calling）

        输出格式：
        [
            {
                "type": "function",
                "function": {
                    "name": "get_technical_indicators",
                    "description": "...",
                    "parameters": {
                        "type": "object",
                        "properties": { ... },
                        "required": [...]
                    }
                }
            },
            ...
        ]
        """
        cls._ensure_loaded()
        skills = cls.get_skills_for_expert(expert_type)
        if not skills:
            return []

        tools = []
        for skill in skills:
            properties = {}
            required = []
            for p in skill.params:
                prop: dict[str, Any] = {
                    "type": cls._TYPE_MAP.get(p.type, "string"),
                }
                if p.description:
                    prop["description"] = p.description
                properties[p.name] = prop
                if p.required:
                    required.append(p.name)

            func_def: dict[str, Any] = {
                "name": skill.name,
                "description": skill.description,
            }
            # 即使无参数也要给 parameters（部分厂商要求）
            func_def["parameters"] = {
                "type": "object",
                "properties": properties,
            }
            if required:
                func_def["parameters"]["required"] = required

            tools.append({
                "type": "function",
                "function": func_def,
            })

        return tools

    # ─── 执行 ───────────────────────────────────────────

    @classmethod
    async def execute(cls, name: str, params: dict, context: Optional[dict] = None) -> str:
        """统一执行入口

        Args:
            name: 工具名
            params: LLM 传入的参数（已解析的 dict）
            context: 执行上下文（如 data_engine 实例、ensure_snapshot 方法等）

        Returns:
            JSON 字符串结果
        """
        cls._ensure_loaded()
        skill = cls._skills.get(name)
        if not skill:
            return json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)

        # 参数校验 + 类型转换
        validated_params = {}
        for p in skill.params:
            val = params.get(p.name, p.default)
            if val is None and p.required:
                # 不硬报错，给个警告让 LLM 兜底
                logger.warning(f"Skill {name} 缺少必要参数: {p.name}")
            if val is not None:
                try:
                    validated_params[p.name] = cls._coerce_type(val, p.type)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Skill {name} 参数 {p.name} 类型转换失败: {e}")
                    validated_params[p.name] = val
            elif p.default is not None:
                validated_params[p.name] = p.default

        # 合并上下文
        ctx = context or {}

        try:
            # 调用 handler
            sig = inspect.signature(skill.handler)
            # 如果 handler 接受 **ctx 或 **kwargs，传入 context
            call_kwargs = {**validated_params}
            for param_name, param in sig.parameters.items():
                if param_name in ctx and param_name not in call_kwargs:
                    call_kwargs[param_name] = ctx[param_name]
                elif param.kind == inspect.Parameter.VAR_KEYWORD:
                    # **kwargs — 把整个 context 传进去
                    call_kwargs.update(ctx)
                    break

            result = skill.handler(**call_kwargs)
            if inspect.isawaitable(result):
                result = await result

            # 确保返回字符串
            if not isinstance(result, str):
                result = json.dumps(result, ensure_ascii=False, default=str)

            # ── 数据校验：自动验证返回数据质量 ──
            try:
                from engine.expert.data_validator import DataValidator
                result = DataValidator.validate(name, result)
            except Exception as ve:
                logger.debug(f"数据校验跳过({name}): {ve}")

            return result

        except Exception as e:
            logger.error(f"Skill {name} 执行异常: {e}")
            return json.dumps({"error": f"工具 {name} 执行失败: {e}"}, ensure_ascii=False)

    # ─── 内部辅助 ────────────────────────────────────────

    @classmethod
    def _coerce_type(cls, val: Any, target_type: str) -> Any:
        """简单类型转换"""
        if target_type == "str":
            return str(val)
        elif target_type == "int":
            return int(val)
        elif target_type == "float":
            return float(val)
        elif target_type == "bool":
            if isinstance(val, str):
                return val.lower() in ("true", "1", "yes")
            return bool(val)
        elif target_type == "dict":
            if isinstance(val, dict):
                return val
            if isinstance(val, str):
                return json.loads(val)
        return val

    @classmethod
    def _ensure_loaded(cls):
        """确保所有 Skill 模块已被 import（触发装饰器注册）"""
        if cls._initialized:
            return
        cls._initialized = True
        try:
            # 导入 skills 包会触发其中所有 @register 装饰器
            import engine.expert.skills  # noqa: F401
            logger.info(f"🔧 SkillRegistry 已加载 {len(cls._skills)} 个 Skill: "
                        f"{list(cls._skills.keys())}")
        except Exception as e:
            logger.warning(f"🔧 SkillRegistry 加载 skills 失败: {e}")

    @classmethod
    def reset(cls):
        """测试用：重置注册表"""
        cls._skills.clear()
        cls._initialized = False
