import datetime
import enum

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TaskType(str, enum.Enum):
    TEXT_TO_TEXT = "text-to-text"
    IMAGE_TO_IMAGE = "image-to-image"
    IMAGE_TO_VIDEO = "image-to-video"
    TEXT_TO_VIDEO = "text-to-video"
    TEXT_TO_IMAGE = "text-to-image"


class ResourceProfile(str, enum.Enum):
    """资源档位：S=1卡 / M=2卡 / L=4卡 / XL=8卡（gang scheduling，整组分配）；
    API=外部模型 API，不占用本机 GPU。"""

    S = "S"
    M = "M"
    L = "L"
    XL = "XL"
    API = "API"


class TaskStatus(str, enum.Enum):
    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    QUEUED = "QUEUED"
    ALLOCATING = "ALLOCATING"
    RUNNING = "RUNNING"
    ENCODING = "ENCODING"
    UPLOADING = "UPLOADING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    task_type: Mapped[str] = mapped_column(String(32), index=True)
    model_key: Mapped[str] = mapped_column(String(64), default="")
    model_version: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(16), default=TaskStatus.CREATED.value, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=5)  # 1 最高
    resource_profile: Mapped[str] = mapped_column(String(4), default=ResourceProfile.S.value)
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    stage: Mapped[str] = mapped_column(String(64), default="")
    gpu_ids: Mapped[str] = mapped_column(String(128), default="")  # "0,1,2,3"
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class TaskInput(Base):
    __tablename__ = "task_inputs"

    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id"), primary_key=True)
    input_asset_ids: Mapped[list] = mapped_column(JSON, default=list)
    prompt: Mapped[str] = mapped_column(Text, default="")
    negative_prompt: Mapped[str] = mapped_column(Text, default="")
    params: Mapped[dict] = mapped_column(JSON, default=dict)


class TaskOutput(Base):
    __tablename__ = "task_outputs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id"), index=True)
    asset_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uri: Mapped[str] = mapped_column(String(512), default="")
    model_version: Mapped[str] = mapped_column(String(64), default="")
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    runtime_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
