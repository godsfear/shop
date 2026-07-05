import uuid

from pydantic import BaseModel

from .base import CreatorMixin, ReadMixin


class EntityBase(BaseModel):
    category: uuid.UUID
    code: str
    name: str | None = None
    description: str | None = None
    table: str
    objectid: uuid.UUID
    value: dict | None = None


class EntityCreate(EntityBase):
    pass


class EntityUpdate(BaseModel):
    category: uuid.UUID | None = None
    code: str | None = None
    name: str | None = None
    description: str | None = None
    table: str | None = None
    objectid: uuid.UUID | None = None
    value: dict | None = None


class EntityFilter(BaseModel):
    category: uuid.UUID | None = None
    code: str | None = None
    table: str | None = None
    objectid: uuid.UUID | None = None


class Entity(EntityBase, ReadMixin, CreatorMixin):
    pass
