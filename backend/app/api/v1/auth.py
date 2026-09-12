from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import audit, get_client_ip, get_current_user
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.user import Token, UserCreate, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

# 默认管理员：admin / admin123（生产环境必须通过环境变量/首次登录修改）


@router.post("/register", response_model=UserOut)
def register(body: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(409, "用户名已存在")
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        role=body.role if body.role in ("user", "creator") else "creator",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login(body: dict, db: Session = Depends(get_db), ip: str = Depends(get_client_ip)):
    username = body.get("username", "")
    password = body.get("password", "")
    user = db.query(User).filter(User.username == username).first()
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    audit(db, user.id, "login", ip=ip)
    return Token(
        access_token=create_access_token(str(user.id), user.role),
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
