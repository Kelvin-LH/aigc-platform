"""任务服务：TaskSpec 校验 → 模型档位解析 → 持久化 → 入队。"""
from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.asset import Asset
from app.models.model_registry import ModelInfo
from app.models.task import Task, TaskInput, TaskType
from app.scheduler.scheduler import scheduler

settings = get_settings()

# 资源档位与任务类型的默认映射（方案 §4 资源池）
PROFILE_MAP: dict[str, str] = {
    TaskType.TEXT_TO_TEXT.value: "S",
    TaskType.TEXT_TO_IMAGE.value: "M",
    TaskType.IMAGE_TO_IMAGE.value: "M",
    TaskType.IMAGE_TO_VIDEO.value: "L",
    TaskType.TEXT_TO_VIDEO.value: "L",
}
# high 质量的视频任务升到 8 卡整组执行
HIGH_VIDEO_PROFILE = "XL"

ALLOWED_IMAGE_MIME = {"image/png", "image/jpeg", "image/webp", "image/bmp"}

TASK_LABELS = {
    TaskType.IMAGE_TO_IMAGE.value: "图生图",
    TaskType.IMAGE_TO_VIDEO.value: "图生视频",
}


def validate_task_spec(db: Session, spec) -> None:
    needs_image = spec.task_type in (TaskType.IMAGE_TO_IMAGE, TaskType.IMAGE_TO_VIDEO)
    if not spec.prompt.strip() and not needs_image:
        raise HTTPException(422, "prompt 不能为空")
    if needs_image:
        if not spec.input_asset_ids:
            raise HTTPException(422, f"{TASK_LABELS.get(spec.task_type.value, spec.task_type.value)}至少需要一张参考图")
        for asset_id in spec.input_asset_ids:
            asset = db.get(Asset, asset_id)
            if asset is None:
                raise HTTPException(422, f"素材不存在: {asset_id}")
            if asset.type != "image":
                raise HTTPException(422, f"素材 {asset_id} 不是图片（type={asset.type}）")
            if asset.mime not in ALLOWED_IMAGE_MIME:
                raise HTTPException(422, f"不支持的图片格式: {asset.mime}")


def resolve_model(db: Session, task_type: str, quality_tier: str) -> ModelInfo:
    """按能力 + 质量档位解析模型；找不到启用模型时报错。
    同档位多个模型时取最新注册的（后注册的 API 模型优先生效）。"""
    q = db.query(ModelInfo).filter(
        ModelInfo.capability == task_type,
        ModelInfo.quality_tier == quality_tier,
        ModelInfo.enabled.is_(True),
    ).order_by(ModelInfo.id.desc())
    model = q.first() or db.query(ModelInfo).filter(
        ModelInfo.capability == task_type, ModelInfo.enabled.is_(True)
    ).order_by(ModelInfo.id.desc()).first()
    if model is None:
        raise HTTPException(503, f"能力 {task_type} 暂无可用模型")
    return model


def create_task(db: Session, user_id: int, spec) -> Task:
    validate_task_spec(db, spec)
    model = resolve_model(db, spec.task_type, spec.model_profile)

    resource_profile = model.resource_profile or PROFILE_MAP.get(spec.task_type, "S")
    if spec.model_profile == "high" and spec.task_type in (
        TaskType.IMAGE_TO_VIDEO.value, TaskType.TEXT_TO_VIDEO.value
    ):
        resource_profile = HIGH_VIDEO_PROFILE  # 高质量视频独占 8 卡

    task_id = str(uuid.uuid4())
    task = Task(
        id=task_id,
        project_id=spec.project_id,
        user_id=user_id,
        task_type=spec.task_type,
        model_key=model.name,
        model_version=model.version,
        priority=max(1, min(spec.priority, 9)),
        resource_profile=resource_profile,
    )
    db.add(task)
    db.add(TaskInput(
        task_id=task_id,
        input_asset_ids=spec.input_asset_ids,
        prompt=spec.prompt,
        negative_prompt=spec.negative_prompt,
        params=spec.generation_params,
    ))
    db.commit()
    return task
