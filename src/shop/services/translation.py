"""Переводы пользовательского контента (см. tables.Translation).

Выдача с локалью — словарь {поле: перевод}; фолбэк на базовое поле объекта
(Entity.name и т.п.) выполняет вызывающий: переводы — надстройка, не замена.
Поиск — trigram ILIKE по контенту выбранной локали.
"""
import uuid
from typing import List

from fastapi import Depends, HTTPException, status
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import db_helper
from ..versioning import versioned_update
from .. import tables
from ..models.translation import TranslationSearch, TranslationSet


def _escape_like(q: str) -> str:
    return q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


class TranslationService:
    def __init__(self, session: AsyncSession = Depends(db_helper.scoped_session_dependency)):
        self.session = session

    async def set_translations(self, table: str, objectid: uuid.UUID,
                               items: List[TranslationSet]) -> List[tables.Translation]:
        """Upsert набора переводов объекта; правка существующего — версионно."""
        results = []
        for item in items:
            language = await self._language_id(item.language)
            row = (await self.session.execute(
                select(tables.Translation).where(
                    tables.Translation.table == table,
                    tables.Translation.objectid == objectid,
                    tables.Translation.field == item.field,
                    tables.Translation.language == language,
                ))).scalar_one_or_none()
            if row is None:
                row = tables.Translation(table=table, objectid=objectid,
                                         field=item.field, language=language,
                                         content=item.content)
                self.session.add(row)
            else:
                row = await versioned_update(self.session, tables.Translation,
                                             row.id, {'content': item.content})
            results.append(row)
        await self.session.commit()
        return results

    async def get_translations(self, table: str, objectid: uuid.UUID,
                               locale: str) -> dict[str, str]:
        """Переводы объекта на локаль: {поле: перевод}."""
        language = await self._language_id(locale)
        rows = (await self.session.execute(
            select(tables.Translation.field, tables.Translation.content).where(
                tables.Translation.table == table,
                tables.Translation.objectid == objectid,
                tables.Translation.language == language,
            ))).all()
        return {row[0]: row[1] for row in rows}

    async def search(self, params: TranslationSearch) -> List[tables.Translation]:
        """Поиск объектов по переводу на локали (trigram ILIKE)."""
        language = await self._language_id(params.locale)
        conditions = [
            tables.Translation.language == language,
            tables.Translation.field == params.field,
            tables.Translation.content.ilike(f'%{_escape_like(params.q)}%', escape='\\'),
        ]
        if params.table is not None:
            conditions.append(tables.Translation.table == params.table)
        rows = (await self.session.execute(
            select(tables.Translation).where(and_(*conditions)).limit(params.limit)
        )).scalars().all()
        return list(rows)

    async def _language_id(self, iso: str) -> uuid.UUID:
        language = (await self.session.execute(
            select(tables.Language.id).where(
                func.lower(tables.Language.iso) == iso.lower()))).scalar_one_or_none()
        if language is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"локаль '{iso}' не заведена в справочнике Language")
        return language
