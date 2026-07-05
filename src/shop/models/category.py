import uuid

from pydantic import BaseModel

from .base import CreatorMixin, ReadMixin


class CategoryBase(BaseModel):
    category: uuid.UUID | None = None  # None — корневая категория
    code: str
    name: str | None = None
    description: str | None = None
    value: dict | None = None


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    category: uuid.UUID | None = None
    code: str | None = None
    name: str | None = None
    description: str | None = None
    value: dict | None = None


class CategoryFilter(BaseModel):
    category: uuid.UUID | None = None
    code: str | None = None


class Category(CategoryBase, ReadMixin, CreatorMixin):
    pass
