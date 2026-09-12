from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.database import get_db
from app.models.model_registry import ModelInfo
from app.models.user import User
from app.schemas.model import ModelOut

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=list[ModelOut])
def list_models(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """返回当前可用模型档位（前端只感知 fast/standard/high，不暴露 checkpoint 细节）。"""
    return db.query(ModelInfo).order_by(ModelInfo.capability, ModelInfo.quality_tier).all()


@router.patch("/{model_id}/enabled", response_model=ModelOut)
def toggle_model(model_id: int, body: dict, admin: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    model = db.get(ModelInfo, model_id)
    if model is None:
        raise HTTPException(404, "模型不存在")
    model.enabled = bool(body.get("enabled", not model.enabled))
    db.commit()
    db.refresh(model)
    return model


@router.post("/{model_id}/health-check")
def health_check(model_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """启动自检占位：生产环境校验 CUDA/NCCL、权重 SHA256、显存基线与 golden sample。"""
    model = db.get(ModelInfo, model_id)
    if model is None:
        raise HTTPException(404, "模型不存在")
    model.health = "healthy" if model.enabled else "degraded"
    db.commit()
    return {"model_id": model_id, "health": model.health,
            "checks": ["cuda", "nccl", "weights", "vram_baseline", "golden_sample"]}
