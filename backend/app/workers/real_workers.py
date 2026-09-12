"""
真实模型 Worker 适配器：将 TaskSpec 转换为本地模型推理调用（V100 FP16 路径）。

- qwen  : Qwen2.5-3B-Instruct（文生文，S 档 1 卡）
- sdxl  : stable-diffusion-xl-base-1.0（文生图，M 档 2 卡，用首卡）
- 其余 adapter（flux_kontext / wan22 等）未部署时回落 mock 流水线。

模型目录约定：$MODEL_ROOT/<name>（默认 ~/models）。目录缺失或依赖缺失时 get_runner
返回 None，调度器自动回落 mock —— 保证平台"先跑通编排、再逐步接入模型"的路线。
模型常驻显存（按 (adapter, gpu) 缓存），避免重复加载。
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import time
import uuid
from pathlib import Path

log = logging.getLogger("worker")

def _model_root() -> Path:
    # 优先环境变量，其次 Settings（.env 中的 MODEL_ROOT），默认 ~/models
    env = os.environ.get("MODEL_ROOT")
    if env:
        return Path(env)
    try:
        from app.core.config import get_settings
        s = get_settings().MODEL_ROOT
        if s:
            return Path(s)
    except Exception:
        pass
    return Path.home() / "models"


MODEL_ROOT = _model_root()
MODEL_DIRS = {
    "qwen": MODEL_ROOT / "Qwen2.5-3B-Instruct",
    "sdxl": MODEL_ROOT / "stable-diffusion-xl-base-1.0",
}
RESULTS_DIR = Path("results/generated")

# (adapter, gpu_id) -> 已加载模型（常驻）
_cache: dict[tuple, object] = {}

# 模型加载必须串行：transformers/diffusers 低内存加载（meta device）不支持并发 .to()，
# 并发加载会抛 NotImplementedError。推理阶段不受锁影响，仍可多卡并发。
import threading

_load_lock = threading.Lock()


def qwen_available() -> bool:
    return (MODEL_DIRS["qwen"] / "config.json").exists()


def sdxl_available() -> bool:
    return (MODEL_DIRS["sdxl"] / "model_index.json").exists()


def get_runner(adapter: str, task_type: str):
    """返回该 (adapter, task_type) 的异步推理函数；未部署返回 None → 调度器回落 mock。"""
    if adapter == "qwen" and task_type == "text-to-text" and qwen_available():
        return run_qwen
    if adapter == "sdxl" and task_type == "text-to-image" and sdxl_available():
        return run_sdxl
    # OpenAI 兼容外部 API（OpenAI / DeepSeek 等），配置了 API Key 即启用
    if adapter in ("openai_api", "deepseek_api") and task_type == "text-to-text" and _api_key(adapter):
        return run_openai_api
    return None


# ---------------- 外部 LLM API（OpenAI 兼容协议） ----------------

def _api_config(adapter: str) -> tuple[str, str, str]:
    if adapter == "deepseek_api":
        return (
            os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com"),
            os.environ.get("DEEPSEEK_API_KEY", ""),
            os.environ.get("DEEPSEEK_API_MODEL", "deepseek-chat"),
        )
    return (
        os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1"),
        os.environ.get("OPENAI_API_KEY", ""),
        os.environ.get("OPENAI_API_MODEL", "gpt-4o-mini"),
    )


def _api_key(adapter: str) -> bool:
    return bool(_api_config(adapter)[1])


async def run_openai_api(db, task, ti, on_stage, cancel_check, gpu_ids) -> dict:
    """OpenAI 兼容 /chat/completions 调用；不占用 GPU（resource_profile=API）。"""
    import httpx

    started = time.perf_counter()
    await on_stage("调用模型 API", 40)
    if cancel_check():
        raise InterruptedError("canceled")

    adapter = "openai_api"
    try:
        from app.models.model_registry import ModelInfo
        m = db.query(ModelInfo).filter(ModelInfo.name == task.model_key).first()
        if m is not None:
            adapter = m.adapter
    except Exception:
        pass
    base, key, model_name = _api_config(adapter)

    params = ti.params or {}
    body = {
        "model": model_name,
        "messages": [{"role": "user", "content": ti.prompt}],
        "max_tokens": int(params.get("max_tokens", 1024)),
        "temperature": float(params.get("temperature", 0.7)),
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            base.rstrip("/") + "/chat/completions",
            json=body,
            headers={"Authorization": f"Bearer {key}"},
        )
    resp.raise_for_status()
    if cancel_check():
        raise InterruptedError("canceled")

    answer = resp.json()["choices"][0]["message"]["content"]
    await on_stage("写回历史", 90)
    out_dir = RESULTS_DIR / "text"
    out_dir.mkdir(parents=True, exist_ok=True)
    fn = out_dir / f"{uuid.uuid4().hex}.txt"
    fn.write_text(answer, encoding="utf-8")
    return {
        "seed": int(params.get("seed", 0)),
        "runtime_ms": int((time.perf_counter() - started) * 1000),
        "output_hint": f"/files/{fn.relative_to('results').as_posix()}",
        "text": answer,
        "model_version": model_name,
    }


# ---------------- Qwen 文生文 ----------------

def _load_qwen(gpu_id: int):
    with _load_lock:
        if ("qwen", gpu_id) in _cache:
            return _cache[("qwen", gpu_id)]
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        d = str(MODEL_DIRS["qwen"])
        log.info("loading Qwen from %s -> cuda:%d", d, gpu_id)
        tok = AutoTokenizer.from_pretrained(d)
        model = AutoModelForCausalLM.from_pretrained(
            d, torch_dtype=torch.float16, device_map={"": gpu_id}
        )
        model.eval()
        _cache[("qwen", gpu_id)] = (tok, model)
        return tok, model


async def run_qwen(db, task, ti, on_stage, cancel_check, gpu_ids) -> dict:
    import torch

    gpu = gpu_ids[0]
    started = time.perf_counter()
    await on_stage("加载模型", 15)
    key = ("qwen", gpu)
    if key not in _cache:
        _cache[key] = await asyncio.to_thread(_load_qwen, gpu)
    tok, model = _cache[key]
    if cancel_check():
        raise InterruptedError("canceled")

    await on_stage("Prompt 编码", 35)
    params = ti.params or {}
    messages = [{"role": "user", "content": ti.prompt}]
    prompt_text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tok([prompt_text], return_tensors="pt").to(model.device)
    max_new_tokens = int(params.get("max_tokens", 512))
    temperature = float(params.get("temperature", 0.7))

    await on_stage("文本生成", 55)

    def _generate():
        with torch.no_grad():
            return model.generate(
                **inputs, max_new_tokens=max_new_tokens, do_sample=True,
                temperature=temperature, top_p=0.9,
                pad_token_id=tok.eos_token_id,
            )

    output_ids = await asyncio.to_thread(_generate)
    if cancel_check():
        raise InterruptedError("canceled")
    answer = tok.decode(output_ids[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)

    await on_stage("写回历史", 90)
    out_dir = RESULTS_DIR / "text"
    out_dir.mkdir(parents=True, exist_ok=True)
    fn = out_dir / f"{uuid.uuid4().hex}.txt"
    fn.write_text(answer, encoding="utf-8")
    return {
        "seed": int(params.get("seed", 0)),
        "runtime_ms": int((time.perf_counter() - started) * 1000),
        "output_hint": f"/files/{fn.relative_to('results').as_posix()}",
        "text": answer,
    }


# ---------------- SDXL 文生图 ----------------

def _load_sdxl(gpu_id: int):
    with _load_lock:
        if ("sdxl", gpu_id) in _cache:
            return _cache[("sdxl", gpu_id)]
        import torch
        from diffusers import StableDiffusionXLPipeline

        d = str(MODEL_DIRS["sdxl"])
        log.info("loading SDXL from %s -> cuda:%d", d, gpu_id)
        pipe = StableDiffusionXLPipeline.from_pretrained(
            d, torch_dtype=torch.float16, use_safetensors=True, variant="fp16"
        )
        pipe.to(f"cuda:{gpu_id}")
        # V100 16GB 显存优化（兼容新旧 diffusers API）
        if hasattr(pipe, "enable_attention_slicing"):
            pipe.enable_attention_slicing()
        if hasattr(pipe, "vae") and hasattr(pipe.vae, "enable_slicing"):
            pipe.vae.enable_slicing()
        if hasattr(pipe, "enable_vae_slicing"):
            pipe.enable_vae_slicing()
        _cache[("sdxl", gpu_id)] = pipe
        return pipe


async def run_sdxl(db, task, ti, on_stage, cancel_check, gpu_ids) -> dict:
    import torch

    # 从分配到的候选卡中选显存最空闲的一张：GPU 管理器只跟踪任务占用，
    # 不感知其他模型常驻显存（如 GPU0 上的 Qwen），按实际余量选卡避免 OOM
    def _pick_gpu() -> int:
        best, best_free = gpu_ids[0], -1
        for g in gpu_ids:
            free, _total = torch.cuda.mem_get_info(g)
            if free > best_free:
                best, best_free = g, free
        return best

    gpu = await asyncio.to_thread(_pick_gpu)
    started = time.perf_counter()
    await on_stage("加载模型", 15)
    key = ("sdxl", gpu)
    if key not in _cache:
        _cache[key] = await asyncio.to_thread(_load_sdxl, gpu)
    pipe = _cache[key]
    if cancel_check():
        raise InterruptedError("canceled")

    params = ti.params or {}
    seed = int(params.get("seed", random.randint(0, 2**31 - 1)))
    steps = max(1, int(params.get("steps", 25)))
    cfg = float(params.get("cfg", 5.0))
    width = int(params.get("width", 1024))
    height = int(params.get("height", 1024))

    def _generate(w: int, h: int):
        generator = torch.Generator(device=f"cuda:{gpu}")
        generator.manual_seed(seed)
        return pipe(
            prompt=ti.prompt,
            negative_prompt=ti.negative_prompt or None,
            num_inference_steps=steps,
            guidance_scale=cfg,
            width=w, height=h,
            generator=generator,
        ).images[0]

    await on_stage("Prompt 编码", 35)
    await on_stage("扩散采样", 55)
    try:
        image = await asyncio.to_thread(_generate, width, height)
    except torch.OutOfMemoryError:
        # 显存不足自动降级到 768 再试一次
        await on_stage("显存不足，降级 768 重试", 55)
        torch.cuda.empty_cache()
        image = await asyncio.to_thread(_generate, 768, 768)
    if cancel_check():
        raise InterruptedError("canceled")
    await on_stage("VAE 解码", 85)

    out_dir = RESULTS_DIR / "image"
    out_dir.mkdir(parents=True, exist_ok=True)
    fn = out_dir / f"{uuid.uuid4().hex}.png"
    await asyncio.to_thread(image.save, fn)
    return {
        "seed": seed,
        "runtime_ms": int((time.perf_counter() - started) * 1000),
        "output_hint": f"/files/{fn.relative_to('results').as_posix()}",
        "image_size": f"{image.width}x{image.height}",
    }
