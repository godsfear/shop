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


# язык базовых полей (Category.name, Entity.name) в сиде/БД; переводы — надстройка
BASE_LANG = 'ru'
# якорный язык фолбэка: запрошенный -> en -> базовое поле
ANCHOR_LANG = 'en'


def primary_language(accept: str | None) -> str:
    """Первый язык из Accept-Language ('en-US,en;q=0.9' -> 'en'); пусто — базовый."""
    if not accept:
        return BASE_LANG
    return accept.split(',')[0].split(';')[0].split('-')[0].strip().lower() or BASE_LANG


async def resolve(session: AsyncSession, table: str, ids, lang: str,
                  ) -> dict[tuple[uuid.UUID, str], str]:
    """Переводы объектов одним запросом: {(objectid, field): content}.

    Запрошенный язык поверх якорного (en); фолбэк на базовое поле (ru) —
    обязанность вызывающего: tr.get((id, field), базовое). Для базового языка
    вызывать не нужно (переводов ru нет — базовые поля и есть ru)."""
    ids = list(ids)
    if not ids:
        return {}
    rows = (await session.execute(
        select(tables.Translation.objectid, tables.Translation.field,
               tables.Translation.content, tables.Language.iso)
        .join(tables.Language, tables.Language.id == tables.Translation.language)
        .where(tables.Translation.table == table,
               tables.Translation.objectid.in_(ids),
               func.lower(tables.Language.iso).in_({lang, ANCHOR_LANG})))).all()
    out: dict[tuple[uuid.UUID, str], str] = {}
    for oid, field, content, iso in rows:
        if iso.lower() == lang or (oid, field) not in out:
            out[(oid, field)] = content
    return out


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
