"""Админ-инструменты. Пока — read-only статистика «сколько в базе чего».

Гейт — require_admin (роль admin в JWT). Первый админ назначается вне API:
python -m shop.grant_admin <email> (см. grant_admin.py) — API set_roles сам
требует админа, иначе курица-яйцо.

Считаем осмысленные величины (не «сырые» таблицы): псевдонимы создаются пачками
заранее (анти-корреляция), поэтому «выдано» = всего − свободный пул; эпизоды —
это Entity на псевдониме (у словарных Entity table='category'); документы лежат
в Data; «мед. факты» — все Property (симптомы/показатели/сон/питание/…).
"""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import db_helper
from ..services.auth import require_admin
from .. import tables

router = APIRouter(prefix='/admin', tags=['admin'],
                   dependencies=[Depends(require_admin)])


@router.get('/stats')
async def stats(session: AsyncSession = Depends(db_helper.scoped_session_dependency)
                ) -> dict[str, int]:
    async def count(model: type, *where) -> int:
        q = select(func.count()).select_from(model)
        # версионируемые (Base): только живые строки — не копии и не погашенные
        if hasattr(model, 'version_of'):
            q = q.where(model.version_of.is_(None), model.ends.is_(None))
        for w in where:
            q = q.where(w)
        return (await session.execute(q)).scalar_one()

    T = tables
    minted = await count(T.Pseudonym)            # всего сгенерировано (буфер + выданные)
    pool_free = await count(T.PseudonymPool)     # свободные в пуле
    return {
        # люди и учётки
        'users': await count(T.User),
        'users_confirmed': await count(T.User, T.User.confirmed.is_(True)),
        'persons': await count(T.Person),
        # псевдонимы (обезличенные якори; создаются заранее пачками)
        'pseudonyms_issued': max(0, minted - pool_free),
        'pseudonyms_pool_free': pool_free,
        # медицинские данные пользователей
        'episodes': await count(T.Entity, T.Entity.table == 'pseudonym'),
        'medical_facts': await count(T.Property),
        'documents': await count(T.Data),
        'consents': await count(T.Consent),
        'keys': await count(T.Key),
        # справочник/система (из сида, не пользовательское)
        'dictionary_items': await count(T.Entity, T.Entity.table == 'category'),
        'translations': await count(T.Translation),
    }
