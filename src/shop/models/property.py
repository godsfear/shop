import datetime
import uuid
from pydantic import BaseModel


class PropertyBase(BaseModel):
    table: str
    object: uuid.UUID
    code: str
    name: str
    value: str
    value_int: int
    value_dec: float
    value_dt: datetime.datetime
    begins: datetime.datetime
    ends: datetime.datetime


class Property(PropertyBase):
    id: uuid.UUID

    class Config:
        orm_mode = True


class PropertyCreate(PropertyBase):
    pass


class PropertyUpdate(PropertyBase):
    pass
