import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(32), default="creator")  # admin / creator / user / auditor
    status: Mapped[str] = mapped_column(String(16), default="active")
    quota_daily: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
