import datetime

from pydantic import BaseModel, ConfigDict


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int | None
    owner_id: int
    type: str
    filename: str
    uri: str
    thumbnail_uri: str | None = None
    sha256: str
    size_bytes: int
    mime: str
    created_at: datetime.datetime | None = None
