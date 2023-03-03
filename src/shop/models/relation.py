import datetime
import uuid
from pydantic import BaseModel


class RelationBase(BaseModel):
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
    id: uuid.UUID

    class Config:
        orm_mode = True


class RelationCreate(RelationBase):
    pass


class RelationUpdate(RelationBase):
    pass
