"""全局配置：开发环境默认零依赖（SQLite + 内存队列），生产通过环境变量切换。"""
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "AIGC Platform"
    API_V1_PREFIX: str = "/api/v1"
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12

    # PostgreSQL in production; SQLite keeps local dev dependency-free.
    DATABASE_URL: str = "sqlite:///./aigc_platform.db"

    REDIS_URL: str = "redis://localhost:6379/0"
    USE_REDIS: bool = False  # True 时使用 Redis 队列/锁，False 时使用进程内实现

    # MinIO / S3
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "aigc-assets"
    USE_MINIO: bool = False  # False 时本地磁盘存储 results/

    # 8x V100 GPU 资源池
    TOTAL_GPUS: int = 8

    # 真实模型权重根目录（real_workers 使用）
    MODEL_ROOT: str = ""

    # 上传限制
    MAX_UPLOAD_MB: int = 200

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
