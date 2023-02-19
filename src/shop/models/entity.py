import uuid
from pydantic import BaseModel


class EntityBase(BaseModel):
    category: str
    code: str
    name: str
    description: str | None


class Entity(EntityBase):
    id: uuid.UUID

    class Config:
        orm_mode = True


class EntityCreate(EntityBase):
    pass


class EntityUpdate(EntityBase):
    pass
