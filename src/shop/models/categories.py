import uuid
from pydantic import BaseModel
from typing import Optional


class CategoriesBase(BaseModel):
    name: str
    description: Optional[str]


class Categories(CategoriesBase):
    id: uuid.UUID

    class Config:
        orm_mode = True


class CategoriesCreate(CategoriesBase):
    pass


class CategoriesUpdate(CategoriesBase):
    pass
