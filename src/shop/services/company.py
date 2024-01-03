import uuid
from datetime import datetime
from typing import List
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_

from ..database import db_helper
from .. import tables
from ..models.company import CompanyCreate, CompanyUpdate, CompanyBase


class CompanyService:
    def __init__(self, session: AsyncSession = Depends(db_helper.scoped_session_dependency)):
        self.session = session

    async def get_all(self) -> List[tables.Company]:
        async with self.session as db:
            async with db.begin():
                query = select(tables.Company)
                res = await db.execute(query)
                company = res.scalars().all()
        return company

    async def get_by_country_code(self, company_data: CompanyBase) -> List[tables.Company]:
        async with self.session as db:
            async with db.begin():
                query = (
                    select(tables.Company).
                    where(
                        and_(
                            tables.Company.country == company_data.country,
                            tables.Company.code == company_data.code
                        )
                    )
                )
                res = await db.execute(query)
                company = res.scalars().all()
        return company

    async def get_by_id(self, company_id: uuid.UUID) -> tables.Company:
        async with self.session as db:
            async with db.begin():
                query = select(tables.Company).where(tables.Company.id == company_id)
                res = await db.execute(query)
                company = res.fetchone()
        if not company:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return company[0]

    async def create(self, company_data: CompanyCreate) -> tables.Company:
        company = tables.Company(**company_data.dict())
        async with self.session as db:
            async with db.begin():
                db.add(company)
                await db.flush()
        return company

    async def update(self, company_id: uuid.UUID, company_data: CompanyUpdate) -> tables.Company:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Company)
                    .where(tables.Company.id == company_id)
                    .values(**company_data.dict())
                    .returning(tables.Company)
                )
                res = await db.execute(query)
                company = res.fetchone()
                if not company:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return company

    async def expire(self, company_id: uuid.UUID) -> tables.Company:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Company)
                    .where(tables.Company.id == company_id)
                    .values(ends=datetime.utcnow())
                    .returning(tables.Company)
                )
                res = await db.execute(query)
                company = res.fetchone()
                if not company:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return company
