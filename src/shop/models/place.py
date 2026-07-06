import uuid

from pydantic import BaseModel

from .base import CreatorMixin, ReadMixin


class PlaceBase(BaseModel):
    category: uuid.UUID | None = None
    code: str
    name: str | None = None
    description: str | None = None
    country: uuid.UUID


class PlaceCreate(PlaceBase):
    pass


class PlaceUpdate(BaseModel):
    category: uuid.UUID | None = None
    code: str | None = None
    name: str | None = None
    description: str | None = None
    country: uuid.UUID | None = None


class PlaceFilter(BaseModel):
    country: uuid.UUID | None = None
    code: str | None = None
    name: str | None = None


class Place(PlaceBase, ReadMixin, CreatorMixin):
    pass
