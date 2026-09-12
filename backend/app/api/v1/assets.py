import hashlib
import json
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.models.asset import Asset
from app.models.user import User
from app.schemas.asset import AssetOut

router = APIRouter(prefix="/assets", tags=["assets"])

settings = get_settings()

ALLOWED_MIME = {
    "image/png": "image", "image/jpeg": "image", "image/webp": "image", "image/bmp": "image",
    "video/mp4": "video", "text/plain": "text",
}


@router.post("", response_model=AssetOut)
async def upload_asset(file: UploadFile, project_id: int | None = None,
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    mime = file.content_type or ""
    if mime not in ALLOWED_MIME:
        raise HTTPException(415, f"不支持的文件类型: {mime or '未知'}")
    data = await file.read()
    if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"文件超过 {settings.MAX_UPLOAD_MB}MB 限制")

    sha256 = hashlib.sha256(data).hexdigest()
    ext = os.path.splitext(file.filename or "")[1][:16] or ".bin"
    key = f"uploads/{uuid.uuid4().hex}{ext}"

    if settings.USE_MINIO:
        from minio import Minio
        import io
        client = Minio(settings.MINIO_ENDPOINT, settings.MINIO_ACCESS_KEY,
                       settings.MINIO_SECRET_KEY, secure=False)
        if not client.bucket_exists(settings.MINIO_BUCKET):
            client.make_bucket(settings.MINIO_BUCKET)
        client.put_object(settings.MINIO_BUCKET, key, io.BytesIO(data), len(data), mime)
        uri = f"s3://{settings.MINIO_BUCKET}/{key}"
    else:
        path = os.path.join("results", key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        uri = f"/files/{key}"

    asset = Asset(
        project_id=project_id,
        owner_id=user.id,
        type=ALLOWED_MIME[mime],
        filename=(file.filename or "asset")[:256],
        uri=uri,
        sha256=sha256,
        size_bytes=len(data),
        mime=mime,
        metadata_json=json.dumps({"ext": ext}),
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@router.get("", response_model=list[AssetOut])
def list_assets(type: str | None = None, limit: int = 50,
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Asset).order_by(Asset.created_at.desc())
    if user.role != "admin":
        q = q.filter(Asset.owner_id == user.id)
    if type:
        q = q.filter(Asset.type == type)
    return q.limit(min(limit, 200)).all()


@router.get("/{asset_id}", response_model=AssetOut)
def get_asset(asset_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    asset = db.get(Asset, asset_id)
    if asset is None or (user.role != "admin" and asset.owner_id != user.id):
        raise HTTPException(404, "素材不存在")
    return asset


@router.delete("/{asset_id}")
def delete_asset(asset_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    asset = db.get(Asset, asset_id)
    if asset is None or (user.role != "admin" and asset.owner_id != user.id):
        raise HTTPException(404, "素材不存在")
    db.delete(asset)
    db.commit()
    return {"deleted": asset_id}
