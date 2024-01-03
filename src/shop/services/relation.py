import uuid
from datetime import datetime
from typing import List
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_

from ..database import db_helper
from .. import tables
from ..models.relation import RelationCreate, RelationUpdate, RelationBase


class RelationService:
    def __init__(self, session: AsyncSession = Depends(db_helper.scoped_session_dependency)):
        self.session = session

    async def get_by_src(self, relation_data: RelationBase) -> List[tables.Relation]:
        async with self.session as db:
            async with db.begin():
                query = (
                    select(tables.Relation).
                    where(
                        and_(
                            tables.Relation.category == relation_data.category,
                            tables.Relation.code == relation_data.code,
                            tables.Relation.src == relation_data.src,
                            tables.Relation.trg == relation_data.trg,
                            tables.Relation.src_id == relation_data.src_id
                        )
                    )
                )
                res = await db.execute(query)
                relation = res.scalars().all()
        return relation

    async def get_by_trg(self, relation_data: RelationBase) -> List[tables.Relation]:
        async with self.session as db:
            async with db.begin():
                query = (
                    select(tables.Relation).
                    where(
                        and_(
                            tables.Relation.category == relation_data.category,
                            tables.Relation.code == relation_data.code,
                            tables.Relation.src == relation_data.src,
                            tables.Relation.trg == relation_data.trg,
                            tables.Relation.src_id == relation_data.trg_id
                        )
                    )
                )
                res = await db.execute(query)
                relation = res.scalars().all()
        return relation

    async def get_by_id(self, relation_id: uuid.UUID) -> tables.Relation:
        async with self.session as db:
            async with db.begin():
                query = select(tables.Relation).where(tables.Relation.id == relation_id)
                res = await db.execute(query)
                relation = res.fetchone()
        if not relation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return relation[0]

    async def create(self, relation_data: RelationCreate) -> tables.Relation:
        relation = tables.Relation(**relation_data.dict())
        async with self.session as db:
            async with db.begin():
                db.add(relation)
                await db.flush()
        return relation

    async def update(self, relation_id: uuid.UUID, relation_data: RelationUpdate) -> tables.Relation:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Relation)
                    .where(tables.Relation.id == relation_id)
                    .values(**relation_data.dict())
                    .returning(tables.Relation)
                )
                res = await db.execute(query)
                relation = res.fetchone()
                if not relation:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return relation

    async def expire(self, relation_id: uuid.UUID) -> tables.Relation:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Relation)
                    .where(tables.Relation.id == relation_id)
                    .values(ends=datetime.utcnow())
                    .returning(tables.Relation)
                )
                res = await db.execute(query)
                relation = res.fetchone()
                if not relation:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return relation
