import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), index=True, nullable=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # image / video / text / audio
    type: Mapped[str] = mapped_column(String(16), index=True)
    filename: Mapped[str] = mapped_column(String(256))
    uri: Mapped[str] = mapped_column(String(512))
    thumbnail_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    mime: Mapped[str] = mapped_column(String(64), default="")
    metadata_json: Mapped[str] = mapped_column(String(2048), default="{}")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
