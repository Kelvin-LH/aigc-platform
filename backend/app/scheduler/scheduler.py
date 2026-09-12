"""
调度器主循环：从优先级队列取任务 → gang scheduling 分配整组 GPU → 执行 Worker →
状态机推进（QUEUED→ALLOCATING→RUNNING→ENCODING→UPLOADING→SUCCEEDED）→ 广播进度事件。

并发设计：
- predicate 调度：队首资源不足时跳过它调度后续可运行任务，消除队头阻塞（XL 等整机空闲，
  不阻塞 S/M/L 小任务；S/M 任务在 8 卡内自然并发）。
- 每个任务独立 asyncio.Task + 独立 DB 会话，互不阻塞；GPU 分配由 GPUManager 内部锁串行化。
- 取消语义：排队任务直接置 CANCELED；运行中任务由 Worker 在阶段边界检查后中断，GPU 必然释放。
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.task import Task, TaskInput, TaskOutput, TaskStatus
from app.scheduler.gpu_manager import EventBus, GPUManager, TaskQueue
from app.workers.mock_workers import run_mock_pipeline

log = logging.getLogger("scheduler")

TERMINAL_STATUSES = {TaskStatus.SUCCEEDED.value, TaskStatus.FAILED.value, TaskStatus.CANCELED.value}


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

    async def submit(self, db: Session, task: Task, priority: int) -> None:
        """入队并持久化 QUEUED 状态（调用方持有 task 所属会话）。"""
        task.status = TaskStatus.QUEUED.value
        task.stage = "排队中"
        db.commit()
        await self.queue.push(task.id, priority, task.resource_profile)
        await self._emit(task.id, TaskStatus.QUEUED, "排队中", 0)

    async def cancel(self, task_id: str) -> bool:
        """取消：排队任务立即落库 CANCELED；运行中任务在下一阶段边界中断。"""
        self._canceled.add(task_id)
        await self.queue.remove(task_id)
        if task_id in self._running:
            return True  # 运行中：由 Worker 的 cancel_check 触发中断与落库
        db = SessionLocal()
        try:
            task = db.get(Task, task_id)
            if task is not None and task.status not in TERMINAL_STATUSES:
                task.status = TaskStatus.CANCELED.value
                task.stage = "已取消"
                task.error_code = "USER_CANCEL"
                db.commit()
                await self._emit(task_id, TaskStatus.CANCELED, "已取消", task.progress)
                return True
        finally:
            db.close()
        return False

    def is_canceled(self, task_id: str) -> bool:
        return task_id in self._canceled

    async def start(self) -> None:
        self._loop_task = asyncio.create_task(self._dispatch_loop())

    async def stop(self) -> None:
        self._stopping = True
        if self._loop_task:
            self._loop_task.cancel()
        for t in list(self._running.values()):
            t.cancel()

    def snapshot(self) -> dict:
        """调度器运行视图（监控页使用）。"""
        return {"queued": len(self.queue), "running": len(self._running)}

    # ---------- 内部逻辑 ----------

    async def _dispatch_loop(self) -> None:
        while not self._stopping:
            try:
                task_id, profile = await self.queue.pop(predicate=self._runnable_now)
                fut = asyncio.create_task(self._run_task(task_id, profile))
                self._running[task_id] = fut
                fut.add_done_callback(lambda _t, tid=task_id: self._running.pop(tid, None))
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("dispatch error")
                await asyncio.sleep(1)

    async def _runnable_now(self, task_id: str, profile: str) -> bool:
        return self.gpu.can_acquire(profile)

    async def _run_task(self, task_id: str, profile: str) -> None:
        db = SessionLocal()
        try:
            task = db.get(Task, task_id)
            if task is None or task.status in TERMINAL_STATUSES:
                return
            gpu_ids = await self.gpu.acquire(profile)
            if gpu_ids is None:
                # predicate 与 acquire 之间的竞态兜底：放回队列稍后重试
                if not self.is_canceled(task_id):
                    await self.queue.push(task_id, task.priority, profile)
                return

            task.gpu_ids = ",".join(map(str, gpu_ids))
            task.status = TaskStatus.ALLOCATING.value
            task.stage = f"已分配 GPU: {task.gpu_ids}"
            db.commit()
            await self._emit(task_id, TaskStatus.ALLOCATING, task.stage, 0, task.gpu_ids)

            try:
                output = await self._execute(db, task, gpu_ids)
            except InterruptedError:
                self._finish(db, task, TaskStatus.CANCELED, "USER_CANCEL", "用户取消")
                await self._emit(task_id, TaskStatus.CANCELED, "已取消", task.progress, task.gpu_ids)
                return
            except asyncio.CancelledError:
                self._finish(db, task, TaskStatus.CANCELED, "SHUTDOWN", "调度器停止")
                raise
            except Exception as e:  # noqa: BLE001
                log.exception("task %s failed", task_id)
                self._finish(db, task, TaskStatus.FAILED, "EXEC_ERROR", str(e))
                await self._emit(task_id, TaskStatus.FAILED, "执行失败", task.progress, task.gpu_ids,
                                 error_code="EXEC_ERROR")
                return
            finally:
                await self.gpu.release(gpu_ids)
                self._canceled.discard(task_id)
                # 资源释放后唤醒调度循环：让等待整机空闲的 XL 等任务立即重试分配
                await self.queue.notify()

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

        # 按模型注册表的 adapter 选择真实推理；未部署（依赖/权重缺失）回落 mock 流水线
        from app.models.model_registry import ModelInfo
        from app.workers import real_workers

        model = db.query(ModelInfo).filter(ModelInfo.name == task.model_key).first()
        runner = real_workers.get_runner(model.adapter, task.task_type) if model else None
        if runner is not None:
            ti = db.get(TaskInput, task.id)
            result = await runner(db, task, ti, on_stage, cancel_check=lambda: self.is_canceled(task.id),
                                  gpu_ids=gpu_ids)
        else:
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

    def _finish(self, db: Session, task: Task, status: TaskStatus, code: str, message: str) -> None:
        task.status = status.value
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

    def current_state(self, task_id: str) -> dict | None:
        """读取任务当前状态（供 SSE 订阅时补发快照，避免重连后事件断档）。"""
        db = SessionLocal()
        try:
            t = db.get(Task, task_id)
            if t is None:
                return None
            return {
                "task_id": t.id, "status": t.status, "stage": t.stage or "",
                "progress": t.progress, "gpu_ids": t.gpu_ids, "error_code": t.error_code,
            }
        finally:
            db.close()


# 进程内单例（uvicorn 单 worker 模式下可用；多 worker/多机部署切换 Redis 队列）
scheduler = Scheduler(GPUManager())
