import datetime
import uuid
from pydantic import BaseModel


class CategoryBase(BaseModel):
    category: str
    code: str
    name: str
    value: str | None
    description: str | None
    begins: datetime.datetime
    ends: datetime.datetime | None
    author: uuid.UUID


class Category(CategoryBase):
    id: uuid.UUID

    class Config:
        orm_mode = True


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(CategoryBase):
    pass
