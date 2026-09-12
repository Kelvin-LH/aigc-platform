"""生成入口：文生文（同步流式）+ 图生图 / 图生视频 / 文生视频（异步 task_id）。"""
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import audit, get_client_ip, get_current_user
from app.core.database import get_db
from app.models.task import TaskStatus, TaskType
from app.models.user import User
from app.scheduler.scheduler import scheduler
from app.schemas.task import TaskCreate, TaskOut
from app.services.task_service import create_task

router = APIRouter(prefix="/generate", tags=["generate"])

ASYNC_TYPES = {TaskType.IMAGE_TO_IMAGE, TaskType.IMAGE_TO_VIDEO, TaskType.TEXT_TO_VIDEO, TaskType.TEXT_TO_IMAGE}


@router.post("/text", response_model=TaskOut)
async def generate_text(body: TaskCreate, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db), ip: str = Depends(get_client_ip)):
    """文生文：统一走任务体系（worker 模拟流式阶段），最终结果写回任务历史。"""
    if body.task_type != TaskType.TEXT_TO_TEXT:
        body.task_type = TaskType.TEXT_TO_TEXT
    task = create_task(db, user.id, body)
    await scheduler.submit(db, task, task.priority)
    audit(db, user.id, "submit_task", "task", task.id, ip, body.task_type)
    return task


@router.post("/image-edit", response_model=TaskOut)
async def generate_image_edit(body: TaskCreate, user: User = Depends(get_current_user),
                              db: Session = Depends(get_db), ip: str = Depends(get_client_ip)):
    body.task_type = TaskType.IMAGE_TO_IMAGE
    task = create_task(db, user.id, body)
    await scheduler.submit(db, task, task.priority)
    audit(db, user.id, "submit_task", "task", task.id, ip, body.task_type)
    return task


@router.post("/image-to-video", response_model=TaskOut)
async def generate_i2v(body: TaskCreate, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db), ip: str = Depends(get_client_ip)):
    body.task_type = TaskType.IMAGE_TO_VIDEO
    task = create_task(db, user.id, body)
    await scheduler.submit(db, task, task.priority)
    audit(db, user.id, "submit_task", "task", task.id, ip, body.task_type)
    return task


@router.post("/text-to-video", response_model=TaskOut)
async def generate_t2v(body: TaskCreate, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db), ip: str = Depends(get_client_ip)):
    body.task_type = TaskType.TEXT_TO_VIDEO
    task = create_task(db, user.id, body)
    await scheduler.submit(db, task, task.priority)
    audit(db, user.id, "submit_task", "task", task.id, ip, body.task_type)
    return task


@router.post("/text-to-image", response_model=TaskOut)
async def generate_t2i(body: TaskCreate, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db), ip: str = Depends(get_client_ip)):
    body.task_type = TaskType.TEXT_TO_IMAGE
    task = create_task(db, user.id, body)
    await scheduler.submit(db, task, task.priority)
    audit(db, user.id, "submit_task", "task", task.id, ip, body.task_type)
    return task


@router.get("/text/stream/{task_id}")
async def stream_text(task_id: str, user: User = Depends(get_current_user)):
    """文生文流式输出：SSE 转发任务阶段事件，前端呈现打字机效果。"""
    from asyncio import QueueEmpty

    q = scheduler.bus.subscribe(task_id)

    async def gen():
        try:
            yield f"data: {json.dumps({'stage': '开始生成', 'progress': 0})}\n\n"
            while True:
                try:
                    event = q.get_nowait()
                except QueueEmpty:
                    import asyncio as _a
                    await _a.sleep(0.2)
                    continue
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("status") in (TaskStatus.SUCCEEDED.value, TaskStatus.FAILED.value,
                                           TaskStatus.CANCELED.value):
                    break
        finally:
            scheduler.bus.unsubscribe(task_id, q)

    return StreamingResponse(gen(), media_type="text/event-stream")
