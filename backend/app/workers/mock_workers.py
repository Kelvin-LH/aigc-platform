"""
Mock 推理 Worker：按各能力复现文档定义的结构化阶段（排队→分配GPU→加载模型→编码→采样→解码→上传）。
生产部署时以真实 Adapter（qwen/flux_kontext/wan22）替换 run() 内部实现即可，业务接口不变。
"""
from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable

from app.models.task import TaskType

# 每个任务类型的推理阶段（文案来自方案 §8.5）
STAGES: dict[str, list[str]] = {
    TaskType.TEXT_TO_TEXT.value: ["加载模型", "Prompt 编码", "文本生成", "写回历史"],
    TaskType.IMAGE_TO_IMAGE.value: ["加载模型", "图像编码", "指令编辑采样", "VAE 解码", "上传结果"],
    TaskType.IMAGE_TO_VIDEO.value: ["加载模型", "Prompt 编码", "扩散采样", "VAE 解码", "视频编码", "上传结果"],
    TaskType.TEXT_TO_VIDEO.value: ["加载模型", "Prompt 编码", "扩散采样", "VAE 解码", "视频编码", "上传结果"],
    TaskType.TEXT_TO_IMAGE.value: ["加载模型", "Prompt 编码", "扩散采样", "VAE 解码", "上传结果"],
}


async def run_mock_pipeline(
    task_type: str,
    on_stage: Callable[[str, int], Awaitable[None]],
    cancel_check: Callable[[], bool],
    gpu_ids: list[int],
    params: dict | None = None,
) -> dict:
    """执行模拟推理流水线，返回输出信息。真实部署替换为模型调用。"""
    params = params or {}
    stages = STAGES.get(task_type, ["加载模型", "推理", "上传结果"])
    total = len(stages)
    seed = random.randint(0, 2**31 - 1)
    started = time.perf_counter()
    # 视频参数：时长/分辨率/FPS 写入结果元数据，并按时长放大模拟耗时
    duration = float(params.get("duration", 5))
    fps = int(params.get("fps", 16))
    resolution = str(params.get("resolution", "1280x720"))
    duration_scale = max(0.5, min(duration / 5, 3.0))

    for i, stage in enumerate(stages):
        if cancel_check():
            raise InterruptedError("canceled")
        await on_stage(stage, int(i / total * 90))
        # 模拟该阶段耗时：文本任务轻，视频任务重（与资源档位/时长正相关）
        weight = 0.3 if task_type == TaskType.TEXT_TO_TEXT.value else 0.6 * len(gpu_ids) ** 0.5
        await asyncio.sleep((weight + 0.2) * duration_scale)

    if cancel_check():
        raise InterruptedError("canceled")
    await on_stage("完成", 100)
    return {
        "seed": seed,
        "runtime_ms": int((time.perf_counter() - started) * 1000),
        "output_hint": f"generated/{task_type}/{seed}",
        "video_meta": {"duration_s": duration, "fps": fps, "resolution": resolution},
    }
