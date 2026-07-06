"""Версионные обновления поверх темпоральной модели.

Правило: строка с данным id — ВСЕГДА текущая версия объекта, поэтому все
ссылки на него (FK, полиморфные ссылки, реестр объектов) остаются валидными
при любом числе правок. История — копии строки: перед изменением прежние
значения снимаются в копию (version_of -> id, ends = момент правки), затем
значения применяются к текущей строке, а её begins сдвигается на момент
правки — периоды версий непрерывны. Копии не попадают в реестр объектов
(см. tables._register_new_objects) и скрыты автофильтром ends.

Блокировка: текущая строка берётся SELECT ... FOR UPDATE — конкурентные
правки одного объекта сериализуются. Правка закрытой (ends) строки
невозможна: автофильтр её не находит -> None.

Примечание: копии хранят и чувствительные поля прежних версий
(например, password_hash пользователя) — учитывать при выдаче доступа
к истории.
"""
import uuid
from datetime import datetime, timezone
from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .tables import Base

T = TypeVar('T', bound=Base)


async def versioned_update(session: AsyncSession, cls: type[T],
                           row_id: uuid.UUID, values: dict) -> T | None:
    """Правит текущую строку, сохранив прежние значения копией-версией.

    Возвращает обновлённую текущую строку или None, если активной строки
    с таким id нет. Транзакцией (commit) управляет вызывающий.
    """
    row = (await session.execute(
        select(cls).where(cls.id == row_id).with_for_update()
    )).scalar_one_or_none()
    if row is None:
        return None
    now = datetime.now(timezone.utc)
    snapshot = {
        col.name: getattr(row, col.name)
        for col in cls.__table__.columns
        if col.name not in ('id', 'version_of')
    }
    snapshot['ends'] = now
    session.add(cls(**snapshot, version_of=row.id))
    for key, value in values.items():
        setattr(row, key, value)
    row.begins = now
    return row


async def versioned_expire(session: AsyncSession, cls: type[T],
                           row_id: uuid.UUID) -> T | None:
    """Закрывает текущую строку (ends = now) под блокировкой FOR UPDATE.

    Блокировка сериализует закрытие с конкурентными versioned_update —
    периоды версий остаются непрерывными. Закрытая строка сама является
    терминальной версией; None — активной строки с таким id нет.
    Автор закрытия пока не записывается (нет колонки) — при необходимости
    аудита добавить closed_by. Транзакцией управляет вызывающий.
    """
    row = (await session.execute(
        select(cls).where(cls.id == row_id).with_for_update()
    )).scalar_one_or_none()
    if row is None:
        return None
    row.ends = datetime.now(timezone.utc)
    return row


async def versions(session: AsyncSession, cls: type[T], row_id: uuid.UUID) -> list[T]:
    """История версий строки: копии от старейшей к новейшей (без текущей)."""
    q = (select(cls)
         .where(cls.version_of == row_id)
         .order_by(cls.begins)
         .execution_options(include_expired=True))
    return list((await session.execute(q)).scalars().all())
