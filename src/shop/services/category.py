import uuid
from datetime import datetime
from typing import List
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_

from ..database import get_session
from .. import tables
from ..models.category import CategoryCreate, CategoryUpdate, CategoryBase


class CategoryService:
    def __init__(self, session: AsyncSession = Depends(get_session)):
        self.session = session

    async def get_by_category(self, category_data: CategoryBase) -> List[tables.Category]:
        async with self.session as db:
            async with db.begin():
                query = (
                    select(tables.Category).
                    where(
                        and_(
                            tables.Category.category == category_data.category,
                        )
                    )
                )
                res = await db.execute(query)
                category = res.scalars().all()
        return category

    async def get_by_code(self, category_data: CategoryBase) -> List[tables.Category]:
        async with self.session as db:
            async with db.begin():
                query = (
                    select(tables.Category).
                    where(
                        and_(
                            tables.Category.code == category_data.code,
                        )
                    )
                )
                res = await db.execute(query)
                category = res.scalars().all()
        return category

    async def get_by_category_code(self, category_data: CategoryBase) -> List[tables.Category]:
        async with self.session as db:
            async with db.begin():
                query = (
                    select(tables.Category).
                    where(
                        and_(
                            tables.Category.category == category_data.category,
                            tables.Category.code == category_data.code
                        )
                    )
                )
                res = await db.execute(query)
                category = res.scalars().all()
        return category

    async def get_by_id(self, category_id: uuid.UUID) -> tables.Category:
        async with self.session as db:
            async with db.begin():
                query = select(tables.Category).where(tables.Category.id == category_id)
                res = await db.execute(query)
                category = res.fetchone()
        if not category:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return category[0]

    async def create(self, category_data: CategoryCreate) -> tables.Category:
        category = tables.Category(**category_data.dict())
        async with self.session as db:
            async with db.begin():
                db.add(category)
                await db.flush()
        return category

    async def update(self, category_id: uuid.UUID, category_data: CategoryUpdate) -> tables.Category:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Category)
                    .where(tables.Category.id == category_id)
                    .values(**category_data.dict())
                    .returning(tables.Category)
                )
                res = await db.execute(query)
                category = res.fetchone()
                if not category:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return category

    async def expire(self, category_id: uuid.UUID) -> tables.Category:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Category)
                    .where(tables.Category.id == category_id)
                    .values(ends=datetime.utcnow())
                    .returning(tables.Category)
                )
                res = await db.execute(query)
                category = res.fetchone()
                if not category:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return category
