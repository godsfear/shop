import datetime
import uuid
from pydantic import BaseModel


class DataBase(BaseModel):
    category: uuid.UUID
    code: str
    table: str
    object: uuid.UUID
    name: str
    algorithm: str
    hash: str
    description: str | None
    begins: datetime.datetime
    ends: datetime.datetime | None
    author: uuid.UUID


class Data(DataBase):
    id: uuid.UUID

    class Config:
        orm_mode = True


class DataCreate(DataBase):
    pass


class DataUpdate(DataBase):
    pass
