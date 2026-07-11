"""Полнота анамнеза (данные) + красные флаги (код) — read-only оценка эпизода.

Полнота: секции описаны данными в Category.value['required'] = [{category, scope}].
Секция «заполнена», если на носителе (эпизод или пациент) есть хоть один активный
Property/Relation этого концепта; пустые секции возвращаются как gaps.

Красные флаги — код: обработчик по имени (@redflag_handler, зеркало @fsm_handler),
активный список — в Category.value['red_flags']. Это НЕ состояние и НЕ БД — чистое
вычисление поверх собранных Property. Красный флаг = вычисляемая тревога, не FSM.
"""
import uuid
from typing import Callable

from fastapi import Depends, HTTPException, status
from sqlalchemy import select

from ..database import db_helper
from .. import tables

_redflags: dict[str, Callable] = {}


def redflag_handler(name: str):
    """Регистрирует красный флаг: fn(symptoms: list[Property]) -> bool."""
    def deco(fn: Callable) -> Callable:
        _redflags[name] = fn
        return fn
    return deco


def _present(symptoms) -> set[str]:
    return {p.code for p in symptoms if (p.value or {}).get('status') == 'present'}


@redflag_handler('acs')
def _acs(symptoms) -> bool:
    """Острый коронарный синдром: боль в груди + одышка/потливость."""
    codes = _present(symptoms)
    return 'chest_pain' in codes and bool(codes & {'dyspnea', 'sweating'})


class MedicalService:
    def __init__(self, session=Depends(db_helper.scoped_session_dependency)):
        self.session = session

    async def assess(self, pseudonym_id: uuid.UUID, episode_id: uuid.UUID) -> dict:
        """{gaps: [пустые секции], alerts: [сработавшие флаги]} по эпизоду."""
        episode = await self.session.get(tables.Entity, episode_id)
        if episode is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='эпизод не найден')
        category = await self.session.get(tables.Category, episode.category) \
            if episode.category else None
        cfg = (category.value or {}) if category else {}

        # резолв кодов концептов -> id: секции + symptom (для флагов)
        codes = {r['category'] for r in cfg.get('required', ())} | {'symptom'}
        cat_id = dict((await self.session.execute(select(
            tables.Category.code, tables.Category.id)
            .where(tables.Category.code.in_(codes)))).all())
        # ponytail: коды концептов уникальны (сид под единственным корнем medical);
        # появятся тёзки в других деревьях — резолвить с привязкой к корню

        gaps = []
        for req in cfg.get('required', ()):
            tbl, oid = ('entity', episode_id) if req.get('scope') == 'episode' \
                else ('pseudonym', pseudonym_id)
            if not await self._has_data(cat_id.get(req['category']), tbl, oid):
                gaps.append(req['category'])

        symptoms = (await self.session.execute(select(tables.Property).where(
            tables.Property.table == 'entity',
            tables.Property.objectid == episode_id,
            tables.Property.category == cat_id.get('symptom')))).scalars().all()
        alerts = [name for name in cfg.get('red_flags', ())
                  if name in _redflags and _redflags[name](symptoms)]
        return {'gaps': gaps, 'alerts': alerts}

    async def _has_data(self, category_id, table: str, objectid: uuid.UUID) -> bool:
        """Есть ли активный Property или Relation этого концепта на носителе."""
        if category_id is None:
            return False
        for cls in (tables.Property, tables.Relation):
            q = select(cls).where(cls.category == category_id,
                                   cls.table == table, cls.objectid == objectid).limit(1)
            if (await self.session.execute(q)).scalars().first() is not None:
                return True
        return False
