import uuid
from typing import List
from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status
from sqlalchemy import select
from sqlalchemy import update

from ..database import get_session
from .. import tables
from ..models.products import ProductsCreate, ProductsUpdate


class ProductsService:
    def __init__(self, session: AsyncSession = Depends(get_session)):
        self.session = session

    async def _get(self, product_id: uuid.UUID) -> tables.Products:
        async with self.session as db:
            async with db.begin():
                query = select(tables.Products).where(tables.Products.id == product_id)
                res = await db.execute(query)
                product = res.fetchone()
        if not product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return product[0]

    async def get_all(self) -> List[tables.Products]:
        async with self.session as db:
            async with db.begin():
                query = select(tables.Products)
                res = await db.execute(query)
                products = res.scalars().all()
        return products

    async def get_by_id(self, product_id: uuid.UUID) -> tables.Products:
        product = await self._get(product_id)
        return product

    async def create(self, products_data: ProductsCreate) -> tables.Products:
        products = tables.Products(**products_data.dict())
        async with self.session as db:
            async with db.begin():
                db.add(products)
                await db.flush()
        return products

    async def update(self, product_id: uuid.UUID, product_data: ProductsUpdate) -> tables.Products:
        async with self.session as db:
            async with db.begin():
                query = (
                            update(tables.Products)
                            .where(tables.Products.id == product_id)
                            .values(**product_data.dict())
                            .returning(tables.Products)
                        )
                res = await db.execute(query)
                product = res.fetchone()
                if not product:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return product

    def delete(self, product_id: uuid.UUID):
        pass
        """async with self.session as db:
            async with db.begin():
                query = update(tables.Products).where(id=product_id).values()
                await db.execute(query)"""
