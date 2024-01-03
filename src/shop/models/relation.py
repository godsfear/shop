import datetime
import uuid
from pydantic import BaseModel, ConfigDict


class RelationBase(BaseModel):
    category: str
    code: str
    name: str
    src: str
    src_id: uuid.UUID
    trg: str
    trg_id: uuid.UUID
    begins: datetime.datetime
    ends: datetime.datetime | None
    author: uuid.UUID


class Relation(RelationBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class RelationCreate(RelationBase):
    pass


class RelationUpdate(RelationBase):
    pass
