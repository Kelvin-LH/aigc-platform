from pydantic import BaseModel, ConfigDict


class ModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    capability: str
    name: str
    version: str
    quality_tier: str
    resource_profile: str
    dtype: str
    min_gpus: int
    peak_vram_gb: int
    supports_cpu_offload: bool
    supports_multi_gpu: bool
    license: str
    enabled: bool
    health: str
    adapter: str
