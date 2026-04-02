"""Study REST API — 学习任务 CRUD"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

from engine.study.engine import get_study_engine

router = APIRouter(prefix="/api/v1/study", tags=["study"])


# ─── 请求/响应模型 ────────────────────────────────────

class StudyTaskRequest(BaseModel):
    target: str          # "600519" / "贵州茅台" / "半导体"
    depth: str = "quick"  # "quick" | "deep"


# ─── 端点 ────────────────────────────────────────────

@router.post("/tasks")
async def create_study_task(req: StudyTaskRequest) -> dict:
    """创建学习任务"""
    if not req.target.strip():
        raise HTTPException(status_code=400, detail="target 不能为空")
    if req.depth not in ("quick", "deep"):
        raise HTTPException(status_code=400, detail="depth 必须为 quick 或 deep")

    engine = get_study_engine()
    task = await engine.create_task(req.target.strip(), req.depth)
    return task


@router.get("/tasks")
async def list_study_tasks(status: str = "") -> list[dict]:
    """查询任务列表"""
    engine = get_study_engine()
    return engine.list_tasks(status_filter=status)


@router.get("/tasks/{task_id}")
async def get_study_task(task_id: str) -> dict:
    """查询单个任务详情"""
    engine = get_study_engine()
    result = engine.get_task(task_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.delete("/tasks/{task_id}")
async def cancel_study_task(task_id: str) -> dict:
    """取消/删除任务"""
    engine = get_study_engine()
    result = await engine.cancel_task(task_id)
    return result
