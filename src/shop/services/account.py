import uuid
from datetime import datetime
from typing import List
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_

from ..database import get_session
from .. import tables
from ..models.account import AccountCreate, AccountUpdate, AccountBase


class AccountService:
    def __init__(self, session: AsyncSession = Depends(get_session)):
        self.session = session

    async def get_by_category_code(self, account_data: AccountBase) -> List[tables.Account]:
        async with self.session as db:
            async with db.begin():
                query = (
                    select(tables.Account).
                    where(
                        and_(
                            tables.Account.category == account_data.category,
                            tables.Account.code == account_data.code
                        )
                    )
                )
                res = await db.execute(query)
                account = res.scalars().all()
        return account

    async def get_by_category_code_currency(self, account_data: AccountBase) -> List[tables.Account]:
        async with self.session as db:
            async with db.begin():
                query = (
                    select(tables.Account).
                    where(
                        and_(
                            tables.Account.category == account_data.category,
                            tables.Account.code == account_data.code,
                            tables.Account.currency == account_data.currency,
                        )
                    )
                )
                res = await db.execute(query)
                account = res.scalars().all()
        return account

    async def get_by_issuer(self, account_data: AccountBase) -> List[tables.Account]:
        async with self.session as db:
            async with db.begin():
                query = (
                    select(tables.Account).
                    where(
                        and_(
                            tables.Account.category == account_data.category,
                            tables.Account.code == account_data.code,
                            tables.Account.currency == account_data.currency,
                            tables.Account.issuer_table == account_data.issuer_table,
                            tables.Account.issuer == account_data.issuer,
                        )
                    )
                )
                res = await db.execute(query)
                account = res.scalars().all()
        return account

    async def get_by_id(self, account_id: uuid.UUID) -> tables.Account:
        async with self.session as db:
            async with db.begin():
                query = select(tables.Account).where(tables.Account.id == account_id)
                res = await db.execute(query)
                account = res.fetchone()
        if not account:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return account[0]

    async def create(self, account_data: AccountCreate) -> tables.Account:
        account = tables.Account(**account_data.dict())
        async with self.session as db:
            async with db.begin():
                db.add(account)
                await db.flush()
        return account

    async def update(self, account_id: uuid.UUID, account_data: AccountUpdate) -> tables.Account:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Account)
                    .where(tables.Account.id == account_id)
                    .values(**account_data.dict())
                    .returning(tables.Account)
                )
                res = await db.execute(query)
                account = res.fetchone()
                if not account:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return account

    async def expire(self, account_id: uuid.UUID) -> tables.Account:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Account)
                    .where(tables.Account.id == account_id)
                    .values(ends=datetime.utcnow())
                    .returning(tables.Account)
                )
                res = await db.execute(query)
                account = res.fetchone()
                if not account:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return account
