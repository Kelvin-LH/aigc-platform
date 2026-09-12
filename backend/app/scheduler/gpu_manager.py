"""
GPU 资源池：8×V100 按 S(1)/M(2)/L(4)/XL(8) 档位做 gang scheduling。
整组 GPU 同时获取/释放，不做单卡碎片式抢占；XL 任务要求整机空闲。
"""
from __future__ import annotations

import asyncio

from app.models.task import ResourceProfile

PROFILE_SIZES: dict[str, int] = {
    ResourceProfile.S.value: 1,
    ResourceProfile.M.value: 2,
    ResourceProfile.L.value: 4,
    ResourceProfile.XL.value: 8,
}


class GPUManager:
    def __init__(self, total_gpus: int = 8):
        self.total = total_gpus
        self.free: set[int] = set(range(total_gpus))
        self._lock = asyncio.Lock()

    def size_of(self, profile: str) -> int:
        return PROFILE_SIZES.get(profile, 1)

    def can_acquire(self, profile: str) -> bool:
        """无锁快速判断（用于调度 predicate）；真实分配仍以 acquire 为准。"""
        need = self.size_of(profile)
        if need > len(self.free):
            return False
        if profile == ResourceProfile.XL.value and len(self.free) != self.total:
            return False
        return True

    async def acquire(self, profile: str) -> list[int] | None:
        """获取整组 GPU；失败返回 None（任务继续留在队列）。XL 仅在整机空闲时分配。"""
        async with self._lock:
            if not self.can_acquire(profile):
                return None
            gpu_ids = sorted(self.free)[: self.size_of(profile)]
            self.free -= set(gpu_ids)
            return gpu_ids

    async def release(self, gpu_ids: list[int]) -> None:
        async with self._lock:
            self.free |= set(gpu_ids)

    def snapshot(self) -> dict:
        return {"total": self.total, "free": sorted(self.free), "busy": sorted(set(range(self.total)) - self.free)}


class EventBus:
    """任务进度事件总线：SSE/WebSocket 订阅同一事件流。"""

    def __init__(self):
        self._subscribers: dict[str, set[asyncio.Queue]] = {}

    def subscribe(self, task_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(task_id, set()).add(q)
        return q

    def unsubscribe(self, task_id: str, q: asyncio.Queue) -> None:
        self._subscribers.get(task_id, set()).discard(q)
        if not self._subscribers.get(task_id):
            self._subscribers.pop(task_id, None)

    async def publish(self, task_id: str, event: dict) -> None:
        for q in list(self._subscribers.get(task_id, set())):
            await q.put(event)


class TaskQueue:
    """
    优先级队列（priority 小者先）。
    条目携带 resource_profile，调度循环用 predicate 跳过资源不足的队头任务，
    避免“高优先级 8 卡任务卡住后面所有 1 卡小任务”的队头阻塞。
    """

    def __init__(self):
        self._items: list[tuple[int, float, str, str]] = []  # (priority, seq, task_id, profile)
        self._seq = 0.0
        self._cond = asyncio.Condition()

    async def push(self, task_id: str, priority: int, profile: str) -> None:
        async with self._cond:
            self._seq += 1
            self._items.append((priority, self._seq, task_id, profile))
            self._cond.notify_all()

    async def pop(self, predicate=None) -> tuple[str, str]:
        """返回 (task_id, profile)。predicate(task_id, profile) 过滤当前资源不可运行的任务。"""
        async with self._cond:
            while True:
                if not self._items:
                    await self._cond.wait()
                    continue
                self._items.sort(key=lambda x: (x[0], x[1]))
                if predicate is None:
                    _, _, task_id, profile = self._items.pop(0)
                    return task_id, profile
                for i, (_, _, task_id, profile) in enumerate(self._items):
                    if await predicate(task_id, profile):
                        _, _, tid, prof = self._items.pop(i)
                        return tid, prof
                await self._cond.wait()

    async def remove(self, task_id: str) -> None:
        async with self._cond:
            self._items = [it for it in self._items if it[2] != task_id]

    async def notify(self) -> None:
        """资源状态变化（任务完成释放 GPU）时唤醒调度循环，重试 predicate。"""
        async with self._cond:
            self._cond.notify_all()

    def __len__(self) -> int:
        return len(self._items)
