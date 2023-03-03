import datetime
import uuid
from pydantic import BaseModel


class PropertyBase(BaseModel):
    table: str
    object: uuid.UUID
    code: str
    name: str
    value: str | None
    value_int: int | None
    value_dec: float | None
    value_dt: datetime.datetime | None
    begins: datetime.datetime
    ends: datetime.datetime | None
    author: uuid.UUID


class Property(PropertyBase):
    id: uuid.UUID

    class Config:
        orm_mode = True


class PropertyCreate(PropertyBase):
    pass


class PropertyUpdate(PropertyBase):
    pass
