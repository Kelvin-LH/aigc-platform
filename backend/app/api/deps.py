import datetime

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "未登录")
    try:
        payload = decode_access_token(auth.removeprefix("Bearer "))
    except Exception:
        raise HTTPException(401, "登录已过期")
    user = db.get(User, int(payload["sub"]))
    if user is None or user.status != "active":
        raise HTTPException(401, "用户不可用")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "需要管理员权限")
    return user


def get_client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def audit(db: Session, user_id: int | None, action: str, object_type: str = "",
          object_id: str = "", ip: str = "", detail: str = "") -> None:
    from app.models.audit_log import AuditLog

    db.add(AuditLog(
        user_id=user_id, action=action, object_type=object_type,
        object_id=str(object_id), ip=ip, detail=detail[:1024],
        created_at=datetime.datetime.now(),
    ))
    db.commit()
