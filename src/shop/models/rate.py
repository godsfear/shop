import datetime
import uuid
from pydantic import BaseModel, ConfigDict


class RateBase(BaseModel):
    category: uuid.UUID
    code: str
    table: str
    object: uuid.UUID
    name: str
    value: float
    description: str | None
    begins: datetime.datetime
    ends: datetime.datetime | None
    author: uuid.UUID


class Rate(RateBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class RateCreate(RateBase):
    pass


class RateUpdate(RateBase):
    pass
