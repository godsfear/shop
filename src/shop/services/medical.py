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
from sqlalchemy import and_, or_, select

from ..database import db_helper
from ..medical_seed import medical_concepts
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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='episode_not_found')
        category = await self.session.get(tables.Category, episode.category) \
            if episode.category else None
        cfg = (category.value or {}) if category else {}

        cat_id = await medical_concepts(self.session)  # {code: id} под корнем 'medical'

        required = cfg.get('required', ())
        have = await self._have(
            [cat_id[r['category']] for r in required if r['category'] in cat_id],
            episode_id, pseudonym_id) if required else set()
        gaps = []
        for req in required:
            tbl, oid = ('entity', episode_id) if req.get('scope') == 'episode' \
                else ('pseudonym', pseudonym_id)
            cid = cat_id.get(req['category'])
            if cid is None or (tbl, oid, cid) not in have:
                gaps.append(req['category'])

        # красные флаги — медицинская тревога: любой недостающий кусок конфигурации
        # это ошибка развёртывания, отказывать надо громко, а не молча без alerts
        alerts = []
        if flags := cfg.get('red_flags', ()):
            if missing := [n for n in flags if n not in _redflags]:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                    detail=f'redflag_handler_missing: {missing}')
            if (symptom_id := cat_id.get('symptom')) is None:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                    detail='seed_missing: symptom')
            symptoms = (await self.session.execute(select(tables.Property).where(
                tables.Property.table == 'entity',
                tables.Property.objectid == episode_id,
                tables.Property.category == symptom_id))).scalars().all()
            alerts = [name for name in flags if _redflags[name](symptoms)]
        return {'gaps': gaps, 'alerts': alerts}

    async def _have(self, category_ids: list, episode_id: uuid.UUID,
                    pseudonym_id: uuid.UUID) -> set[tuple]:
        """{(table, objectid, category)} с активными Property/Relation — все
        секции полноты двумя запросами вместо пары запросов на каждую (N+1)."""
        have: set[tuple] = set()
        for cls in (tables.Property, tables.Relation):
            rows = (await self.session.execute(
                select(cls.table, cls.objectid, cls.category).distinct().where(
                    cls.category.in_(category_ids),
                    or_(and_(cls.table == 'entity', cls.objectid == episode_id),
                        and_(cls.table == 'pseudonym', cls.objectid == pseudonym_id))))).all()
            have |= {tuple(r) for r in rows}
        return have
