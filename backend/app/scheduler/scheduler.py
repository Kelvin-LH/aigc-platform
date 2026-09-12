"""
调度器主循环：从优先级队列取任务 → gang scheduling 分配整组 GPU → 执行 Worker →
状态机推进（QUEUED→ALLOCATING→RUNNING→ENCODING→UPLOADING→SUCCEEDED）→ 广播进度事件。
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.asset import Asset
from app.models.task import Task, TaskInput, TaskOutput, TaskStatus
from app.scheduler.gpu_manager import EventBus, GPUManager, TaskQueue
from app.workers.mock_workers import run_mock_pipeline

log = logging.getLogger("scheduler")


class Scheduler:
    def __init__(self, gpu_manager: GPUManager):
        self.gpu = gpu_manager
        self.queue = TaskQueue()
        self.bus = EventBus()
        self._canceled: set[str] = set()
        self._running: dict[str, asyncio.Task] = {}
        self._loop_task: asyncio.Task | None = None
        self._stopping = False

    # ---------- 对外接口（API 层调用） ----------

    async def submit(self, task: Task, priority: int) -> None:
        task.status = TaskStatus.QUEUED.value
        await self.queue.push(task.id, priority)
        await self._emit(task.id, TaskStatus.QUEUED, "排队中", 0)

    async def cancel(self, task_id: str) -> bool:
        """取消排队任务，或中断运行中任务的当前阶段之后继续。"""
        self._canceled.add(task_id)
        await self.queue.remove(task_id)
        return True

    def is_canceled(self, task_id: str) -> bool:
        return task_id in self._canceled

    async def start(self) -> None:
        self._loop_task = asyncio.create_task(self._dispatch_loop())

    async def stop(self) -> None:
        self._stopping = True
        if self._loop_task:
            self._loop_task.cancel()

    # ---------- 内部逻辑 ----------

    async def _dispatch_loop(self) -> None:
        """单进程调度循环：顺序取队首任务，资源不足时等待并让队列重试。"""
        while not self._stopping:
            try:
                task_id = await self.queue.pop()
                asyncio.create_task(self._run_task(task_id))
                await asyncio.sleep(0.05)  # 让 Worker 先占卡，避免同帧重复分配
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("dispatch error")
                await asyncio.sleep(1)

    async def _run_task(self, task_id: str) -> None:
        db = SessionLocal()
        try:
            task = db.get(Task, task_id)
            if task is None or task.status in (TaskStatus.CANCELED.value, TaskStatus.SUCCEEDED.value):
                return
            gpu_ids = await self.gpu.acquire(task.resource_profile)
            if gpu_ids is None:
                # 资源不足：放回队列，稍后重试（XL 任务等待整机空闲）
                await asyncio.sleep(0.5)
                if not self.is_canceled(task_id):
                    await self.queue.push(task_id, task.priority)
                return

            task.gpu_ids = ",".join(map(str, gpu_ids))
            task.status = TaskStatus.ALLOCATING.value
            task.stage = f"已分配 GPU: {task.gpu_ids}"
            db.commit()
            await self._emit(task_id, TaskStatus.ALLOCATING, task.stage, 0, task.gpu_ids)

            try:
                output = await self._execute(db, task, gpu_ids)
            except InterruptedError:
                self._finish_failed(db, task, "CANCELED", "用户取消")
                await self._emit(task_id, TaskStatus.CANCELED, "已取消", task.progress, task.gpu_ids)
                return
            except Exception as e:  # noqa: BLE001
                log.exception("task %s failed", task_id)
                self._finish_failed(db, task, "EXEC_ERROR", str(e))
                await self._emit(task_id, TaskStatus.FAILED, "执行失败", task.progress, task.gpu_ids,
                                 error_code="EXEC_ERROR")
                return
            finally:
                await self.gpu.release(gpu_ids)
                self._canceled.discard(task_id)

            self._finish_succeeded(db, task, output)
            await self._emit(task_id, TaskStatus.SUCCEEDED, "生成完成", 100, task.gpu_ids)
        finally:
            db.close()

    async def _execute(self, db: Session, task: Task, gpu_ids: list[int]) -> dict:
        task.status = TaskStatus.RUNNING.value
        db.commit()

        async def on_stage(stage: str, progress: int) -> None:
            task.stage, task.progress = stage, progress
            db.commit()
            await self._emit(task.id, TaskStatus.RUNNING, stage, progress, task.gpu_ids)

        result = await run_mock_pipeline(
            task.task_type,
            on_stage=on_stage,
            cancel_check=lambda: self.is_canceled(task.id),
            gpu_ids=gpu_ids,
        )

        task.status = TaskStatus.ENCODING.value
        task.stage, task.progress = "结果编码", 95
        db.commit()
        await self._emit(task.id, TaskStatus.ENCODING, task.stage, 95, task.gpu_ids)

        task.status = TaskStatus.UPLOADING.value
        task.stage, task.progress = "保存结果", 99
        db.commit()
        await self._emit(task.id, TaskStatus.UPLOADING, task.stage, 99, task.gpu_ids)
        return result

    def _finish_succeeded(self, db: Session, task: Task, output: dict) -> None:
        task.status = TaskStatus.SUCCEEDED.value
        task.stage, task.progress = "生成完成", 100
        task.model_version = task.model_version or "mock-v1"
        db.add(TaskOutput(
            task_id=task.id,
            uri=output["output_hint"],
            model_version=task.model_version,
            seed=output["seed"],
            runtime_ms=output["runtime_ms"],
        ))
        db.commit()

    def _finish_failed(self, db: Session, task: Task, code: str, message: str) -> None:
        task.status = TaskStatus.FAILED.value if code != "CANCELED" else TaskStatus.CANCELED.value
        task.error_code = code
        task.error_message = message[:512]
        db.commit()

    async def _emit(self, task_id: str, status: TaskStatus, stage: str, progress: int,
                    gpu_ids: str = "", error_code: str | None = None) -> None:
        await self.bus.publish(task_id, {
            "task_id": task_id,
            "status": status.value,
            "stage": stage,
            "progress": progress,
            "gpu_ids": gpu_ids,
            "error_code": error_code,
        })


# 进程内单例（uvicorn 单 worker 模式下可用；多 worker/多机部署切换 Redis 队列）
scheduler = Scheduler(GPUManager())
