"""
Mock 推理 Worker：按各能力复现文档定义的结构化阶段（排队→分配GPU→加载模型→编码→采样→解码→上传）。
生产部署时以真实 Adapter（qwen/flux_kontext/wan22）替换 run() 内部实现即可，业务接口不变。

与真实 Worker 的接口契约一致：mock 也产出真实文件（PNG/MP4/TXT），
保证"生成完成"必然有可预览的结果——预览图/预览视频由本地占位渲染生成。
"""
from __future__ import annotations

import asyncio
import colorsys
import random
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

from app.models.task import TaskType

RESULTS_DIR = Path("results/generated")

# 每个任务类型的推理阶段（文案来自方案 §8.5）
STAGES: dict[str, list[str]] = {
    TaskType.TEXT_TO_TEXT.value: ["加载模型", "Prompt 编码", "文本生成", "写回历史"],
    TaskType.IMAGE_TO_IMAGE.value: ["加载模型", "图像编码", "指令编辑采样", "VAE 解码", "上传结果"],
    TaskType.IMAGE_TO_VIDEO.value: ["加载模型", "Prompt 编码", "扩散采样", "VAE 解码", "视频编码", "上传结果"],
    TaskType.TEXT_TO_VIDEO.value: ["加载模型", "Prompt 编码", "扩散采样", "VAE 解码", "视频编码", "上传结果"],
    TaskType.TEXT_TO_IMAGE.value: ["加载模型", "Prompt 编码", "扩散采样", "VAE 解码", "上传结果"],
}


def _seed_color(seed: int, offset: float = 0.0) -> tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb(((seed % 360) / 360 + offset) % 1.0, 0.55, 0.95)
    return int(r * 255), int(g * 255), int(b * 255)


def _gradient_image(w: int, h: int, seed: int, hue_shift: float = 0.0) -> "Image.Image":
    from PIL import Image

    top, bottom = _seed_color(seed, hue_shift), _seed_color(seed, hue_shift + 0.15)
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        t = y / max(h - 1, 1)
        row = tuple(int(a + (b - a) * t) for a, b in zip(top, bottom))
        for x in range(w):
            px[x, y] = row
    return img


def _label_image(img, lines: list[str]) -> None:
    from PIL import ImageDraw, ImageFont

    draw = ImageDraw.Draw(img)
    h = img.height
    try:
        font = ImageFont.load_default(size=max(18, h // 24))
        small = ImageFont.load_default(size=max(14, h // 40))
    except TypeError:
        font = ImageFont.load_default()
        small = font
    y = h - 30 - len(lines) * (h // 22)
    for i, line in enumerate(lines):
        f = font if i == 0 else small
        draw.text((24, y + i * (h // 22)), line, fill=(255, 255, 255), font=f,
                  stroke_width=2, stroke_fill=(0, 0, 0))


def _write_placeholder_png(path: Path, prompt: str, seed: int, w: int, h: int,
                           hue_shift: float = 0.0, badge: str = "MOCK 预览图") -> None:
    img = _gradient_image(w, h, seed, hue_shift)
    _label_image(img, [badge, f"seed: {seed}", (prompt or "")[:60]])
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def _load_input_image(asset_uri: str):
    """从本地 results/ 加载输入素材（uri 形如 /files/uploads/xxx.png）。"""
    try:
        from PIL import Image

        rel = asset_uri.removeprefix("/files/").split("?")[0]
        p = Path("results") / rel
        if p.exists():
            return Image.open(p).convert("RGB")
    except Exception:
        pass
    return None


def _zoom_frame(img, progress: float, w: int, h: int):
    """以图片为中心做轻微放大裁切，模拟镜头推进。"""
    zoom = 1.0 + 0.12 * progress
    iw, ih = img.size
    cw, ch = int(iw / zoom), int(ih / zoom)
    x0, y0 = (iw - cw) // 2, (ih - ch) // 2
    return img.crop((x0, y0, x0 + cw, y0 + ch)).resize((w, h))


def _write_mock_video(path: Path, prompt: str, seed: int, duration_s: float, fps: int,
                      w: int, h: int, input_image=None) -> None:
    """生成真实 MP4：有参考图时做镜头推进动画，否则生成流动渐变动画。"""
    import numpy as np
    from PIL import ImageDraw, ImageFont

    path.parent.mkdir(parents=True, exist_ok=True)
    total = max(int(duration_s * fps), 2)
    frames = []
    for i in range(total):
        t = i / max(total - 1, 1)
        if input_image is not None:
            frame = _zoom_frame(input_image, t, w, h)
        else:
            frame = _gradient_image(w, h, seed, hue_shift=0.25 * t)
            draw = ImageDraw.Draw(frame)
            try:
                font = ImageFont.load_default(size=max(16, h // 30))
            except TypeError:
                font = ImageFont.load_default()
            draw.text((24, 24), f"{i + 1}/{total}", fill=(255, 255, 255), font=font,
                      stroke_width=2, stroke_fill=(0, 0, 0))
        frames.append(np.asarray(frame))

    import imageio
    with imageio.get_writer(str(path), fps=fps, codec="libx264", quality=7,
                            macro_block_size=8) as writer:
        for f in frames:
            writer.append_data(f)


async def run_mock_pipeline(
    task_type: str,
    on_stage: Callable[[str, int], Awaitable[None]],
    cancel_check: Callable[[], bool],
    gpu_ids: list[int],
    params: dict | None = None,
    prompt: str = "",
    input_assets: list | None = None,
) -> dict:
    """执行模拟推理流水线并产出真实可预览文件，返回输出信息。"""
    params = params or {}
    stages = STAGES.get(task_type, ["加载模型", "推理", "上传结果"])
    total = len(stages)
    seed = random.randint(0, 2**31 - 1)
    started = time.perf_counter()
    duration = float(params.get("duration", 5))
    fps = int(params.get("fps", 16))
    resolution = str(params.get("resolution", "1280x720"))
    w, h = (int(x) for x in resolution.lower().split("x"))
    duration_scale = max(0.5, min(duration / 5, 3.0))

    for i, stage in enumerate(stages):
        if cancel_check():
            raise InterruptedError("canceled")
        await on_stage(stage, int(i / total * 90))
        weight = 0.3 if task_type == TaskType.TEXT_TO_TEXT.value else 0.6 * len(gpu_ids) ** 0.5
        await asyncio.sleep((weight + 0.2) * duration_scale)

    if cancel_check():
        raise InterruptedError("canceled")
    await on_stage("完成", 100)

    prompt = ""
    first_asset_uri = ""
    for a in input_assets or []:
        first_asset_uri = a.uri or ""
        break

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if task_type in (TaskType.IMAGE_TO_VIDEO.value, TaskType.TEXT_TO_VIDEO.value):
        fn = RESULTS_DIR / "video" / f"{uuid.uuid4().hex}.mp4"
        input_image = _load_input_image(first_asset_uri) if first_asset_uri else None
        await asyncio.to_thread(
            _write_mock_video, fn, prompt, seed,
            min(duration, 10), min(fps, 24), w, h, input_image,
        )
        output_hint = f"/files/{fn.relative_to('results').as_posix()}"
        media = {"type": "video", "path": output_hint}
    elif task_type in (TaskType.IMAGE_TO_IMAGE.value, TaskType.TEXT_TO_IMAGE.value):
        fn = RESULTS_DIR / "image" / f"{uuid.uuid4().hex}.png"
        input_image = _load_input_image(first_asset_uri) if first_asset_uri else None
        if input_image is not None:
            img = _zoom_frame(input_image, 0.5, w, h)
            _label_image(img, ["MOCK 编辑结果", f"seed: {seed}", (prompt or "指令式编辑")[:60]])
            fn.parent.mkdir(parents=True, exist_ok=True)
            img.save(fn)
        else:
            await asyncio.to_thread(
                _write_placeholder_png, fn, prompt, seed, w, h,
            )
        output_hint = f"/files/{fn.relative_to('results').as_posix()}"
        media = {"type": "image", "path": output_hint}
    else:  # 文本
        fn = RESULTS_DIR / "text" / f"{uuid.uuid4().hex}.txt"
        fn.parent.mkdir(parents=True, exist_ok=True)
        fn.write_text(
            f"[Mock 模拟输出]\n\n你的输入：{prompt or '（空）'}\n\n"
            "当前为模拟 Worker（未接入真实模型）。接入真实模型后，此处将展示模型生成的完整文本。",
            encoding="utf-8",
        )
        output_hint = f"/files/{fn.relative_to('results').as_posix()}"
        media = {"type": "text", "path": output_hint}

    return {
        "seed": seed,
        "runtime_ms": int((time.perf_counter() - started) * 1000),
        "output_hint": output_hint,
        "video_meta": {"duration_s": duration, "fps": fps, "resolution": resolution},
        "media": media,
    }
