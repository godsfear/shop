import uuid
from datetime import datetime
from typing import List
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_

from ..database import get_session
from .. import tables
from ..models.operation import OperationCreate, OperationUpdate, OperationBase


class OperationService:
    def __init__(self, session: AsyncSession = Depends(get_session)):
        self.session = session

    async def operation_idx(self, operation_data: OperationBase) -> List[tables.Operation]:
        async with self.session as db:
            async with db.begin():
                query = (
                    select(tables.Operation).
                    where(
                        and_(
                            tables.Operation.category == operation_data.category,
                            tables.Operation.code == operation_data.code,
                            tables.Operation.debit == operation_data.debit,
                            tables.Operation.credit == operation_data.credit,
                            tables.Operation.begins.date() == operation_data.begins.date(),
                        )
                    )
                )
                res = await db.execute(query)
                operation = res.scalars().all()
        return operation

    async def operation_db_idx(self, operation_data: OperationBase) -> List[tables.Operation]:
        async with self.session as db:
            async with db.begin():
                query = (
                    select(tables.Operation).
                    where(
                        and_(
                            tables.Operation.category == operation_data.category,
                            tables.Operation.code == operation_data.code,
                            tables.Operation.debit == operation_data.debit,
                            tables.Operation.number == operation_data.number,
                            tables.Operation.begins.date() == operation_data.begins.date(),
                        )
                    )
                )
                res = await db.execute(query)
                operation = res.scalars().all()
        return operation

    async def operation_cr_idx(self, operation_data: OperationBase) -> List[tables.Operation]:
        async with self.session as db:
            async with db.begin():
                query = (
                    select(tables.Operation).
                    where(
                        and_(
                            tables.Operation.category == operation_data.category,
                            tables.Operation.code == operation_data.code,
                            tables.Operation.credit == operation_data.credit,
                            tables.Operation.number == operation_data.number,
                            tables.Operation.begins.date() == operation_data.begins.date(),
                        )
                    )
                )
                res = await db.execute(query)
                operation = res.scalars().all()
        return operation

    async def get_by_id(self, operation_id: uuid.UUID) -> tables.Operation:
        async with self.session as db:
            async with db.begin():
                query = select(tables.Operation).where(tables.Operation.id == operation_id)
                res = await db.execute(query)
                operation = res.fetchone()
        if not operation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return operation[0]

    async def create(self, operation_data: OperationCreate) -> tables.Operation:
        operation = tables.Operation(**operation_data.dict())
        async with self.session as db:
            async with db.begin():
                db.add(operation)
                await db.flush()
        return operation

    async def update(self, operation_id: uuid.UUID, operation_data: OperationUpdate) -> tables.Operation:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Operation)
                    .where(tables.Operation.id == operation_id)
                    .values(**operation_data.dict())
                    .returning(tables.Operation)
                )
                res = await db.execute(query)
                operation = res.fetchone()
                if not operation:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return operation

    async def expire(self, operation_id: uuid.UUID) -> tables.Operation:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Operation)
                    .where(tables.Operation.id == operation_id)
                    .values(ends=datetime.utcnow())
                    .returning(tables.Operation)
                )
                res = await db.execute(query)
                operation = res.fetchone()
                if not operation:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return operation
