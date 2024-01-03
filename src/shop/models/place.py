import datetime
import uuid
from pydantic import BaseModel, ConfigDict


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
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class PlaceCreate(PlaceBase):
    pass


class PlaceUpdate(PlaceBase):
    pass
