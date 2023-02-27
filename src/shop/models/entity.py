import datetime
import uuid
from pydantic import BaseModel


class EntityBase(BaseModel):
    category: str
    code: str
    name: str
    description: str | None
    begins: datetime.datetime
    ends: datetime.datetime


class Entity(EntityBase):
    id: uuid.UUID

    class Config:
        orm_mode = True


class EntityCreate(EntityBase):
    pass


class EntityUpdate(EntityBase):
    pass
