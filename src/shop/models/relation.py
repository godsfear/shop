import uuid

from pydantic import BaseModel

from .base import CreatorMixin, ReadMixin


class RelationBase(BaseModel):
    category: uuid.UUID | None = None
    code: str
    name: str | None = None
    description: str | None = None
    table: str                       # тип объекта-источника
    objectid: uuid.UUID
    related_table: str               # тип объекта-цели
    related_id: uuid.UUID


class RelationCreate(RelationBase):
    pass


class RelationUpdate(BaseModel):
    # концы связи (table/objectid/related_*) — её идентичность; сменить = другая
    # связь (expire + create), поэтому меняем только описательные поля
    code: str | None = None
    name: str | None = None
    description: str | None = None


class RelationFilter(BaseModel):
    table: str | None = None
    objectid: uuid.UUID | None = None
    related_table: str | None = None
    related_id: uuid.UUID | None = None
    category: uuid.UUID | None = None
    code: str | None = None


class Relation(RelationBase, ReadMixin, CreatorMixin):
    pass
