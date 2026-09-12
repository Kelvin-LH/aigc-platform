from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ModelInfo(Base):
    """模型注册表：一个业务能力（capability）可挂多个后端，前端只感知质量档位。"""

    __tablename__ = "models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    capability: Mapped[str] = mapped_column(String(32), index=True)  # text-to-text / image-to-image / ...
    name: Mapped[str] = mapped_column(String(128))
    version: Mapped[str] = mapped_column(String(64), default="v1")
    quality_tier: Mapped[str] = mapped_column(String(16), default="standard")  # fast / standard / high
    resource_profile: Mapped[str] = mapped_column(String(4), default="S")  # S/M/L/XL
    dtype: Mapped[str] = mapped_column(String(16), default="fp16")  # V100: 禁用 fp8，默认 fp16
    min_gpus: Mapped[int] = mapped_column(Integer, default=1)
    peak_vram_gb: Mapped[int] = mapped_column(Integer, default=16)
    supports_cpu_offload: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_multi_gpu: Mapped[bool] = mapped_column(Boolean, default=False)
    license: Mapped[str] = mapped_column(String(256), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    health: Mapped[str] = mapped_column(String(16), default="unknown")  # healthy / degraded / unknown
    adapter: Mapped[str] = mapped_column(String(64), default="mock")  # mock / qwen / flux_kontext / wan22
    default_params: Mapped[str] = mapped_column(String(1024), default="{}")
