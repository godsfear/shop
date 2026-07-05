import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_

from ..database import db_helper
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
        async with self.session as db:
            async with db.begin():
                res = await db.execute(select(tables.Category).where(and_(*conditions)))
                category = res.scalars().all()
        return list(category)

    async def get_by_id(self, category_id: uuid.UUID) -> tables.Category:
        async with self.session as db:
            async with db.begin():
                res = await db.execute(select(tables.Category).where(tables.Category.id == category_id))
                category = res.scalar_one_or_none()
        if category is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return category

    async def create(self, category_data: CategoryCreate) -> tables.Category:
        category = tables.Category(**category_data.model_dump())
        async with self.session as db:
            async with db.begin():
                db.add(category)
                await db.flush()
        return category

    async def update(self, category_id: uuid.UUID, category_data: CategoryUpdate) -> tables.Category:
        values = category_data.model_dump(exclude_unset=True)
        if not values:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Нет полей для обновления')
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Category)
                    .where(tables.Category.id == category_id)
                    .values(**values)
                    .returning(tables.Category)
                )
                res = await db.execute(query)
                category = res.scalar_one_or_none()
                if category is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return category

    async def expire(self, category_id: uuid.UUID) -> tables.Category:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Category)
                    .where(tables.Category.id == category_id)
                    .values(ends=datetime.now(timezone.utc))
                    .returning(tables.Category)
                )
                res = await db.execute(query)
                category = res.scalar_one_or_none()
                if category is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return category
