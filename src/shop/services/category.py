import uuid
from typing import List

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from ..database import db_helper
from ..versioning import versioned_expire, versioned_update
from .. import tables
from ..models.category import CategoryCreate, CategoryUpdate, CategoryFilter


class CategoryService:
    def __init__(self, session: AsyncSession = Depends(db_helper.scoped_session_dependency)):
        self.session = session

    async def find(self, flt: CategoryFilter) -> List[tables.Category]:
        conditions = []
        if flt.category is not None:
            conditions.append(tables.Category.category == flt.category)
        if flt.code is not None:
            conditions.append(tables.Category.code == flt.code)
        if not conditions:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Пустой фильтр')
        res = await self.session.execute(select(tables.Category).where(and_(*conditions)))
        return list(res.scalars().all())

    async def get_by_id(self, category_id: uuid.UUID) -> tables.Category:
        res = await self.session.execute(
            select(tables.Category).where(tables.Category.id == category_id))
        category = res.scalar_one_or_none()
        if category is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return category

    async def create(self, category_data: CategoryCreate,
                     creator: uuid.UUID | None = None) -> tables.Category:
        category = tables.Category(**category_data.model_dump(), creator=creator)
        self.session.add(category)
        await self.session.commit()
        return category

    async def update(self, category_id: uuid.UUID, category_data: CategoryUpdate) -> tables.Category:
        values = category_data.model_dump(exclude_unset=True)
        if not values:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Нет полей для обновления')
        category = await versioned_update(self.session, tables.Category, category_id, values)
        if category is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        await self.session.commit()
        return category

    async def expire(self, category_id: uuid.UUID) -> tables.Category:
        category = await versioned_expire(self.session, tables.Category, category_id)
        if category is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        await self.session.commit()
        return category
