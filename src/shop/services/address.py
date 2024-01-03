import uuid
from datetime import datetime
from typing import List
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_

from ..database import db_helper
from .. import tables
from ..models.address import AddressCreate, AddressUpdate, AddressBase


class AddressService:
    def __init__(self, session: AsyncSession = Depends(db_helper.scoped_session_dependency)):
        self.session = session

    async def get_by_index(self, address_data: AddressBase) -> List[tables.Address]:
        async with self.session as db:
            async with db.begin():
                query = (
                    select(tables.Address).
                    where(
                        and_(
                            tables.Address.country == address_data.country,
                            tables.Address.region == address_data.region,
                            tables.Address.place == address_data.place,
                            tables.Address.postcode == address_data.postcode,
                            tables.Address.street == address_data.street,
                        )
                    )
                )
                res = await db.execute(query)
                address = res.scalars().all()
        return address

    async def get_by_id(self, address_id: uuid.UUID) -> tables.Address:
        async with self.session as db:
            async with db.begin():
                query = select(tables.Address).where(tables.Address.id == address_id)
                res = await db.execute(query)
                address = res.fetchone()
        if not address:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return address[0]

    async def create(self, address_data: AddressCreate) -> tables.Address:
        address = tables.Address(**address_data.dict())
        async with self.session as db:
            async with db.begin():
                db.add(address)
                await db.flush()
        return address

    async def update(self, address_id: uuid.UUID, address_data: AddressUpdate) -> tables.Address:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Address)
                    .where(tables.Address.id == address_id)
                    .values(**address_data.dict())
                    .returning(tables.Address)
                )
                res = await db.execute(query)
                address = res.fetchone()
                if not address:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return address

    async def expire(self, address_id: uuid.UUID) -> tables.Address:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Address)
                    .where(tables.Address.id == address_id)
                    .values(ends=datetime.utcnow())
                    .returning(tables.Address)
                )
                res = await db.execute(query)
                address = res.fetchone()
                if not address:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return address
