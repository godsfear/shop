import uuid
from typing import List
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from starlette import status

from ..database import get_session
from .. import tables
from ..models.categories import CategoriesCreate, CategoriesUpdate


class CategoriesService:
    def __init__(self, session: Session = Depends(get_session)):
        self.session = session

    def _get(self, category_id: uuid.UUID) -> tables.Categories:
        categories = self.session.query(tables.Categories).filter_by(id=category_id).first()
        if not categories:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return categories

    def get_all(self) -> List[tables.Categories]:
        return self.session.query(tables.Categories).all()

    def get_by_id(self, category_id: uuid.UUID) -> tables.Categories:
        return self._get(category_id)

    def create(self, categories_data: CategoriesCreate) -> tables.Categories:
        categories = tables.Categories(**categories_data.dict())
        self.session.add(categories)
        self.session.flush()
        self.session.commit()
        return categories

    def update(self, category_id: uuid.UUID, category_data: CategoriesUpdate) -> tables.Products:
        categories = self._get(category_id)
        for field, value in category_data:
            setattr(categories, field, value)
        self.session.flush()
        self.session.commit()
        return categories

    def delete(self, category_id: uuid.UUID):
        categories = self._get(category_id)
        self.session.delete(categories)
        self.session.commit()
