"""应用入口：lifespan 中启动调度循环、建表并注入种子数据。"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1 import assets, auth, generate, models_api, monitor, tasks
from app.core.config import get_settings
from app.core.database import Base, SessionLocal, engine
from app.scheduler.scheduler import scheduler

logging.basicConfig(level=logging.INFO)
settings = get_settings()


def seed(db) -> None:
    from app.core.security import hash_password
    from app.models.model_registry import ModelInfo
    from app.models.user import User

    if not db.query(User).filter(User.username == "admin").first():
        db.add(User(username="admin", password_hash=hash_password("admin123"), role="admin"))
    if not db.query(User).filter(User.username == "creator").first():
        db.add(User(username="creator", password_hash=hash_password("creator123"), role="creator"))

    defaults = [
        # capability, name, quality_tier, profile, dtype, min_gpus, offload, multi, license, adapter
        ("text-to-text", "Qwen2.5-3B-Instruct", "fast", "S", "fp16", 1, False, False, "Apache-2.0", "qwen"),
        ("text-to-text", "Qwen2.5-7B-Instruct", "standard", "S", "fp16", 1, False, True, "Apache-2.0", "qwen"),
        ("text-to-text", "Qwen2.5-14B-Instruct", "high", "M", "fp16", 2, False, True, "Apache-2.0", "qwen"),
        ("image-to-image", "SDXL+ControlNet", "standard", "M", "fp16", 2, False, False, "OpenRAIL", "sdxl"),
        ("image-to-image", "FLUX.1-Kontext-dev", "high", "L", "fp16", 4, True, True, "FLUX [dev] Non-Commercial", "flux_kontext"),
        ("text-to-image", "SDXL-Base", "standard", "M", "fp16", 2, False, False, "OpenRAIL", "sdxl"),
        ("text-to-image", "FLUX.1-Krea-dev", "high", "L", "fp16", 4, True, True, "FLUX [dev] Non-Commercial", "flux_krea"),
        ("image-to-video", "Wan2.2-TI2V-5B", "standard", "L", "fp16", 4, True, True, "Apache-2.0", "wan22"),
        ("image-to-video", "Wan2.2-I2V-A14B", "high", "XL", "fp16", 8, True, True, "Apache-2.0", "wan22"),
        ("text-to-video", "Wan2.2-T2V-5B", "standard", "L", "fp16", 4, True, True, "Apache-2.0", "wan22"),
        ("text-to-video", "Wan2.2-T2V-A14B", "high", "XL", "fp16", 8, True, True, "Apache-2.0", "wan22"),
    ]
    for cap, name, tier, profile, dtype, min_gpus, offload, multi, lic, adapter in defaults:
        if not db.query(ModelInfo).filter(ModelInfo.name == name).first():
            db.add(ModelInfo(
                capability=cap, name=name, version="v1", quality_tier=tier,
                resource_profile=profile, dtype=dtype, min_gpus=min_gpus,
                supports_cpu_offload=offload, supports_multi_gpu=multi,
                license=lic, adapter=adapter, health="unknown",
            ))
    db.commit()

    # 外部 LLM API 模型（OpenAI 兼容协议）：配置了对应 API Key 才注册并启用；
    # 同档位按 id 倒序取最新（见 task_service.resolve_model），API 模型后来居上
    if os.environ.get("DEEPSEEK_API_KEY"):
        if not db.query(ModelInfo).filter(ModelInfo.name == "DeepSeek-Chat(API)").first():
            db.add(ModelInfo(
                capability="text-to-text", name="DeepSeek-Chat(API)",
                version=os.environ.get("DEEPSEEK_API_MODEL", "deepseek-chat"),
                quality_tier="high", resource_profile="API", dtype="api",
                min_gpus=0, peak_vram_gb=0, license="DeepSeek API", adapter="deepseek_api",
            ))
            db.query(ModelInfo).filter(ModelInfo.name == "Qwen2.5-14B-Instruct") \
                .update({ModelInfo.enabled: False})
    if os.environ.get("OPENAI_API_KEY"):
        if not db.query(ModelInfo).filter(ModelInfo.name == "OpenAI-GPT(API)").first():
            db.add(ModelInfo(
                capability="text-to-text", name="OpenAI-GPT(API)",
                version=os.environ.get("OPENAI_API_MODEL", "gpt-4o-mini"),
                quality_tier="fast", resource_profile="API", dtype="api",
                min_gpus=0, peak_vram_gb=0, license="OpenAI API", adapter="openai_api",
            ))
            db.query(ModelInfo).filter(ModelInfo.name == "Qwen2.5-3B-Instruct") \
                .update({ModelInfo.enabled: False})
    db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()
    await scheduler.start()
    yield
    await scheduler.stop()


app = FastAPI(title=settings.APP_NAME, version="1.0.0", lifespan=lifespan,
              description="AIGC 多模态智能生成平台（8×V100）— 统一入口 / 异步任务 / GPU 调度 / 多模型网关")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_prefix = settings.API_V1_PREFIX
app.include_router(auth.router, prefix=api_prefix)
app.include_router(generate.router, prefix=api_prefix)
app.include_router(tasks.router, prefix=api_prefix)
app.include_router(assets.router, prefix=api_prefix)
app.include_router(models_api.router, prefix=api_prefix)
app.include_router(monitor.router, prefix=api_prefix)

# 本地磁盘存储时对外提供结果文件
app.mount("/files", StaticFiles(directory="results"), name="files")


@app.get("/healthz")
def healthz():
    return {"status": "ok", "gpu_pool": scheduler.gpu.snapshot()}


# 服务器部署时由后端直接托管前端构建产物（frontend/dist），无需独立 node/nginx。
# 必须注册在所有 API 路由（含 /healthz）之后；未知路径回退 index.html（SPA history 路由）。
from pathlib import Path

from fastapi.responses import FileResponse

_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.exists():
    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        candidate = (_dist / full_path).resolve()
        if full_path and candidate.is_file() and str(candidate).startswith(str(_dist.resolve())):
            # 静态资源（带内容哈希）可长缓存
            return FileResponse(candidate, headers={"Cache-Control": "public, max-age=31536000, immutable"})
        # index.html 禁止缓存：前端发版后浏览器立即拉新版本
        return FileResponse(_dist / "index.html", headers={"Cache-Control": "no-cache"})
