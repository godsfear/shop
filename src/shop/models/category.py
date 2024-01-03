import datetime
import uuid
from pydantic import BaseModel, ConfigDict


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
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(CategoryBase):
    pass
