import uuid

from pydantic import BaseModel

from .base import CreatorMixin, ReadMixin


class PropertyBase(BaseModel):
    category: uuid.UUID | None = None
    code: str
    name: str | None = None
    description: str | None = None
    table: str                       # тип объекта-носителя (pseudonym, entity, ...)
    objectid: uuid.UUID
    value: dict


class PropertyCreate(PropertyBase):
    pass


class PropertyUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    description: str | None = None
    value: dict | None = None


class PropertyFilter(BaseModel):
    table: str | None = None
    objectid: uuid.UUID | None = None
    category: uuid.UUID | None = None
    code: str | None = None


class Property(PropertyBase, ReadMixin, CreatorMixin):
    pass
