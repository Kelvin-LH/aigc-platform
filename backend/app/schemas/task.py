import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.task import ResourceProfile, TaskType


class TaskSpec(BaseModel):
    """统一任务规格：业务层只构造 TaskSpec，模型侧 Adapter 转换为具体参数。"""

    task_type: TaskType
    project_id: Optional[int] = None
    input_asset_ids: list[int] = Field(default_factory=list)
    prompt: str = ""
    negative_prompt: str = ""
    model_profile: str = "standard"  # fast / standard / high
    generation_params: dict = Field(default_factory=dict)
    priority: int = 5  # 1 最高
    callback_url: Optional[str] = None


class TaskCreate(TaskSpec):
    pass


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: int | None
    user_id: int
    task_type: str
    model_key: str
    model_version: str
    status: str
    priority: int
    resource_profile: str
    progress: int
    stage: str
    gpu_ids: str
    error_code: str | None = None
    created_at: datetime.datetime | None = None
    updated_at: datetime.datetime | None = None


class TaskStageEvent(BaseModel):
    """SSE/WebSocket 进度事件：结构化阶段而非笼统的“生成中”。"""

    task_id: str
    status: str
    stage: str
    progress: int
    gpu_ids: str = ""
    error_code: str | None = None
