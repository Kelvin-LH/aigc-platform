"""系统监控：GPU 池状态、任务队列、调度器心跳。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.scheduler.gpu_manager import PROFILE_SIZES
from app.scheduler.scheduler import scheduler

router = APIRouter(prefix="/monitor", tags=["monitor"])


@router.get("/gpus")
def gpu_status(user: User = Depends(get_current_user)):
    snap = scheduler.gpu.snapshot()
    return {
        **snap,
        "profiles": {k: v for k, v in PROFILE_SIZES.items()},
        "note": "V100 不支持 MIG：进程级隔离 + CUDA_VISIBLE_DEVICES + gang scheduling",
    }


@router.get("/queue")
def queue_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    by_status = {}
    for s in TaskStatus:
        by_status[s.value] = db.query(Task).filter(Task.status == s.value).count()
    return {
        "tasks": by_status,
        "queued_in_memory": scheduler.snapshot()["queued"],
        "running_now": scheduler.snapshot()["running"],
    }


@router.get("/overview")
def overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """工作台总览：最近任务 + 资源状态。"""
    recent = db.query(Task).order_by(Task.created_at.desc()).limit(10).all()
    return {
        "gpus": scheduler.gpu.snapshot(),
        "recent_tasks": [
            {"id": t.id, "type": t.task_type, "status": t.status,
             "progress": t.progress, "stage": t.stage, "created_at": str(t.created_at)}
            for t in recent
        ],
    }
