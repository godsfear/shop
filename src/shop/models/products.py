from pydantic import BaseModel
from typing import Optional, List
from .categories import Categories


class ProductsBase(BaseModel):
    name: str
    description: Optional[str]


class Products(ProductsBase):
    id: int
    category: Optional[List[Categories]]

    class Config:
        orm_mode = True


class ProductsCreate(ProductsBase):
    pass


class ProductsUpdate(ProductsBase):
    pass
