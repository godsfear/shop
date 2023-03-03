import datetime
import uuid
from pydantic import BaseModel


class PlaceBase(BaseModel):
    category: uuid.UUID
    code: str
    country: uuid.UUID
    name: str
    description: str | None
    begins: datetime.datetime
    ends: datetime.datetime | None
    author: uuid.UUID


class Place(PlaceBase):
    id: uuid.UUID

    class Config:
        orm_mode = True


class PlaceCreate(PlaceBase):
    pass


class PlaceUpdate(PlaceBase):
    pass
