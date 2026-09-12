from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.task import Task, TaskInput, TaskOutput, TaskStatus
from app.models.user import User
from app.scheduler.scheduler import scheduler
from app.schemas.task import TaskOut

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskOut])
def list_tasks(status: str | None = None, task_type: str | None = None,
               limit: int = 50, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    q = db.query(Task).order_by(Task.created_at.desc())
    if user.role != "admin":
        q = q.filter(Task.user_id == user.id)
    if status:
        q = q.filter(Task.status == status)
    if task_type:
        q = q.filter(Task.task_type == task_type)
    return q.limit(min(limit, 200)).all()


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None or (user.role != "admin" and task.user_id != user.id):
        raise HTTPException(404, "任务不存在")
    return task


@router.get("/{task_id}/detail")
def get_task_detail(task_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None or (user.role != "admin" and task.user_id != user.id):
        raise HTTPException(404, "任务不存在")
    task_input = db.get(TaskInput, task_id)
    outputs = db.query(TaskOutput).filter(TaskOutput.task_id == task_id).all()
    return {
        "task": TaskOut.model_validate(task),
        "input": {
            "prompt": task_input.prompt if task_input else "",
            "negative_prompt": task_input.negative_prompt if task_input else "",
            "input_asset_ids": task_input.input_asset_ids if task_input else [],
            "params": task_input.params if task_input else {},
        },
        "outputs": [
            {"id": o.id, "uri": o.uri, "model_version": o.model_version,
             "seed": o.seed, "runtime_ms": o.runtime_ms}
            for o in outputs
        ],
    }


@router.post("/{task_id}/cancel", response_model=TaskOut)
async def cancel_task(task_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None or (user.role != "admin" and task.user_id != user.id):
        raise HTTPException(404, "任务不存在")
    if task.status in (TaskStatus.SUCCEEDED.value, TaskStatus.FAILED.value, TaskStatus.CANCELED.value):
        raise HTTPException(409, f"任务已结束（{task.status}），无法取消")
    await scheduler.cancel(task_id)
    db.refresh(task)
    return task


@router.post("/{task_id}/retry", response_model=TaskOut)
async def retry_task(task_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """重试失败/取消任务：保留原始参数与模型版本，生成新任务。"""
    old = db.get(Task, task_id)
    if old is None or (user.role != "admin" and old.user_id != user.id):
        raise HTTPException(404, "任务不存在")
    if old.status not in (TaskStatus.FAILED.value, TaskStatus.CANCELED.value):
        raise HTTPException(409, "仅失败/取消任务可重试")
    from app.models.task import TaskType
    from app.schemas.task import TaskCreate
    from app.services.task_service import create_task

    ti = db.get(TaskInput, task_id)
    spec = TaskCreate(
        task_type=TaskType(old.task_type),
        project_id=old.project_id,
        input_asset_ids=ti.input_asset_ids if ti else [],
        prompt=ti.prompt if ti else "",
        negative_prompt=ti.negative_prompt if ti else "",
        generation_params=ti.params if ti else {},
        priority=old.priority,
    )
    task = create_task(db, user.id, spec)
    await scheduler.submit(task, task.priority)
    return task


@router.get("/{task_id}/events")
async def task_events(task_id: str, user: User = Depends(get_current_user)):
    """SSE 任务进度事件流。"""
    import asyncio
    import json

    from fastapi.responses import StreamingResponse

    q = scheduler.bus.subscribe(task_id)

    async def gen():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    if event.get("status") in (TaskStatus.SUCCEEDED.value, TaskStatus.FAILED.value,
                                               TaskStatus.CANCELED.value):
                        break
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            scheduler.bus.unsubscribe(task_id, q)

    return StreamingResponse(gen(), media_type="text/event-stream")
