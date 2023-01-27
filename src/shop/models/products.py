import uuid
from pydantic import BaseModel
from typing import Optional, List
from .categories import Categories


class ProductsBase(BaseModel):
    name: str
    description: str | None


class Products(ProductsBase):
    id: uuid.UUID
#  category: List[Categories] | None

    class Config:
        orm_mode = True


class ProductsCreate(ProductsBase):
    pass


class ProductsUpdate(ProductsBase):
    pass
