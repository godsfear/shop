import uuid
from datetime import datetime
from typing import List
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_

from ..database import db_helper
from .. import tables
from ..models.message import MessageCreate, MessageUpdate, MessageBase


class MessageService:
    def __init__(self, session: AsyncSession = Depends(db_helper.scoped_session_dependency)):
        self.session = session

    async def get_by_message_idx(self, message_data: MessageBase) -> List[tables.Message]:
        async with self.session as db:
            async with db.begin():
                query = (
                    select(tables.Message).
                    where(
                        and_(
                            tables.Message.category == message_data.category,
                            tables.Message.code == message_data.code,
                            tables.Message.sender == message_data.author,
                            tables.Message.receiver == message_data.receiver,
                            tables.Message.begins.date() == message_data.begins.date(),
                        )
                    )
                )
                res = await db.execute(query)
                message = res.scalars().all()
        return message

    async def get_by_message_sender_idx(self, message_data: MessageBase) -> List[tables.Message]:
        async with self.session as db:
            async with db.begin():
                query = (
                    select(tables.Message).
                    where(
                        and_(
                            tables.Message.category == message_data.category,
                            tables.Message.code == message_data.code,
                            tables.Message.sender == message_data.author,
                            tables.Message.begins.date() == message_data.begins.date(),
                        )
                    )
                )
                res = await db.execute(query)
                message = res.scalars().all()
        return message

    async def get_by_message_receiver_idx(self, message_data: MessageBase) -> List[tables.Message]:
        async with self.session as db:
            async with db.begin():
                query = (
                    select(tables.Message).
                    where(
                        and_(
                            tables.Message.category == message_data.category,
                            tables.Message.code == message_data.code,
                            tables.Message.receiver == message_data.receiver,
                            tables.Message.begins >= message_data.begins,
                        )
                    )
                )
                res = await db.execute(query)
                message = res.scalars().all()
        return message

    async def get_by_id(self, message_id: uuid.UUID) -> tables.Message:
        async with self.session as db:
            async with db.begin():
                query = select(tables.Message).where(tables.Message.id == message_id)
                res = await db.execute(query)
                message = res.fetchone()
        if not message:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return message[0]

    async def create(self, message_data: MessageCreate) -> tables.Message:
        message = tables.Message(**message_data.dict())
        async with self.session as db:
            async with db.begin():
                db.add(message)
                await db.flush()
        return message

    async def update(self, message_id: uuid.UUID, message_data: MessageUpdate) -> tables.Message:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Message)
                    .where(tables.Message.id == message_id)
                    .values(**message_data.dict())
                    .returning(tables.Message)
                )
                res = await db.execute(query)
                message = res.fetchone()
                if not message:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return message

    async def expire(self, message_id: uuid.UUID) -> tables.Message:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Message)
                    .where(tables.Message.id == message_id)
                    .values(ends=datetime.utcnow())
                    .returning(tables.Message)
                )
                res = await db.execute(query)
                message = res.fetchone()
                if not message:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return message
