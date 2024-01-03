import uuid
from datetime import datetime
from typing import List
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_

from ..database import db_helper
from .. import tables
from ..models.document import DocumentCreate, DocumentUpdate, DocumentBase


class DocumentService:
    def __init__(self, session: AsyncSession = Depends(db_helper.scoped_session_dependency)):
        self.session = session

    async def document_idx(self, document_data: DocumentBase) -> tables.Document:
        async with self.session as db:
            async with db.begin():
                query = (
                    select(tables.Document).
                    where(
                        and_(
                            tables.Document.category == document_data.category,
                            tables.Document.code == document_data.code,
                            tables.Document.country == document_data.country,
                            tables.Document.code == document_data.code,
                            tables.Document.series == document_data.series,
                            tables.Document.number == document_data.number,
                            tables.Document.issue == document_data.issue,
                        )
                    )
                )
                res = await db.execute(query)
                document = res.fetchone()
        return document[0]

    async def document_issuer_idx(self, document_data: DocumentBase) -> List[tables.Document]:
        async with self.session as db:
            async with db.begin():
                query = (
                    select(tables.Document).
                    where(
                        and_(
                            tables.Document.category == document_data.category,
                            tables.Document.code == document_data.code,
                            tables.Document.issuer_table == document_data.issuer_table,
                            tables.Document.issuer == document_data.issuer,
                        )
                    )
                )
                res = await db.execute(query)
                document = res.scalars().all()
        return document

    async def get_by_id(self, document_id: uuid.UUID) -> tables.Document:
        async with self.session as db:
            async with db.begin():
                query = select(tables.Document).where(tables.Document.id == document_id)
                res = await db.execute(query)
                document = res.fetchone()
        if not document:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return document[0]

    async def create(self, document_data: DocumentCreate) -> tables.Document:
        document = tables.Document(**document_data.dict())
        async with self.session as db:
            async with db.begin():
                db.add(document)
                await db.flush()
        return document

    async def update(self, document_id: uuid.UUID, document_data: DocumentUpdate) -> tables.Document:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Document)
                    .where(tables.Document.id == document_id)
                    .values(**document_data.dict())
                    .returning(tables.Document)
                )
                res = await db.execute(query)
                document = res.fetchone()
                if not document:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return document

    async def expire(self, document_id: uuid.UUID) -> tables.Document:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Document)
                    .where(tables.Document.id == document_id)
                    .values(ends=datetime.utcnow())
                    .returning(tables.Document)
                )
                res = await db.execute(query)
                document = res.fetchone()
                if not document:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return document
