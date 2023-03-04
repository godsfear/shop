import datetime
import uuid
from pydantic import BaseModel


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
    id: uuid.UUID

    class Config:
        orm_mode = True


class RateCreate(RateBase):
    pass


class RateUpdate(RateBase):
    pass
