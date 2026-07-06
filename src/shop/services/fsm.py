"""Машина состояний для сущностей.

Раскладка:
- ОПРЕДЕЛЕНИЕ машины — в категории объекта: Category.value['fsm'] =
  {"states": [...], "initial": "...", "transitions": [{"event", "source",
  "dest", "guard"?, "action"?}]}. Категория определяет тип сущности —
  она же определяет и её жизненный цикл.
- ТЕКУЩЕЕ СОСТОЯНИЕ объекта — активная Property-строка (code='state',
  value={'state': ..., 'event': ...}); переход = закрыть старую строку
  (ends) + вставить новую. История переходов — это просто закрытые строки:
  темпоральная модель даёт аудит бесплатно.
- ПЕРЕХОД выполняется в памяти синхронным FSMMixin: сервис грузит
  состояние, гоняет trigger() с guard'ами/action'ами, сохраняет результат.

guard/action в конфиге — имена обработчиков, зарегистрированных через
@fsm_handler; обработчики синхронные: handler(machine, **context), где
machine несёт .table/.objectid, context — kwargs вызова trigger.

Конкурентные trigger по одному объекту сериализуются блокировкой строки
самого объекта (SELECT ... FOR UPDATE в _config при lock=True): второй
переход читает состояние уже после коммита первого.
"""
import uuid
from datetime import datetime, timezone
from typing import Callable

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import db_helper
from ..fsm_mixin import FSMMixin, TransitionError
from .. import tables

STATE_CODE = 'state'

_handlers: dict[str, Callable] = {}
_tables_by_name: dict[str, type] = {}


def fsm_handler(name: str):
    """Регистрирует guard/action, на который могут ссылаться конфиги категорий."""
    def deco(fn: Callable) -> Callable:
        _handlers[name] = fn
        return fn
    return deco


def _machine_class(config: dict) -> type[FSMMixin]:
    """Собирает класс машины из конфига категории; обработчики становятся методами."""
    for spec in config.get('transitions', ()):
        for role in ('guard', 'action'):
            name = spec.get(role)
            if isinstance(name, str) and name not in _handlers:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                    detail=f"обработчик '{name}' не зарегистрирован (@fsm_handler)")
    try:
        return type('CategoryFSM', (FSMMixin,), {
            'states': tuple(config['states']),
            'initial_state': config['initial'],
            'transitions': list(config.get('transitions', ())),
            **_handlers,
        })
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f'некорректная конфигурация машины состояний: {e}')


def _table_class(name: str) -> type:
    if not _tables_by_name:
        _tables_by_name.update(
            (m.class_.__tablename__, m.class_) for m in tables.Base.registry.mappers)
    cls = _tables_by_name.get(name)
    if cls is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"таблицы '{name}' не существует")
    return cls


class FSMService:
    def __init__(self, session: AsyncSession = Depends(db_helper.scoped_session_dependency)):
        self.session = session

    async def state(self, table: str, objectid: uuid.UUID) -> dict:
        """Текущее состояние и доступные события (лениво: без строки — initial)."""
        config = await self._config(table, objectid)
        machine = self._machine(config, table, objectid,
                                await self._current_row(table, objectid))
        return {'state': machine.state, 'available': machine.available_events()}

    async def trigger(self, table: str, objectid: uuid.UUID, event: str,
                      creator: uuid.UUID | None = None, **context) -> dict:
        """Переход: закрывает активную строку состояния и пишет новую.
        Строка объекта блокируется — конкурентные переходы сериализуются."""
        config = await self._config(table, objectid, lock=True)
        row = await self._current_row(table, objectid)
        machine = self._machine(config, table, objectid, row)
        try:
            new_state = machine.trigger(event, **context)
        except TransitionError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
        if row is not None:
            row.ends = datetime.now(timezone.utc)
        self.session.add(tables.Property(
            table=table, objectid=objectid, code=STATE_CODE,
            value={'state': new_state, 'event': event}, creator=creator))
        await self.session.commit()
        return {'state': new_state, 'available': machine.available_events()}

    async def history(self, table: str, objectid: uuid.UUID) -> list[tables.Property]:
        """Все состояния объекта, включая закрытые, в порядке наступления."""
        q = (select(tables.Property)
             .where(tables.Property.table == table,
                    tables.Property.objectid == objectid,
                    tables.Property.code == STATE_CODE)
             .order_by(tables.Property.begins)
             .execution_options(include_expired=True))
        return list((await self.session.execute(q)).scalars().all())

    # ------------------------------------------------------------------ #
    async def _config(self, table: str, objectid: uuid.UUID, lock: bool = False) -> dict:
        cls = _table_class(table)
        q = select(cls).where(cls.id == objectid)
        if lock:
            q = q.with_for_update()
        obj = (await self.session.execute(q)).scalar_one_or_none()
        if obj is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='объект не найден')
        category_id = getattr(obj, 'category', None)
        if category_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail='у объекта нет категории — машина состояний не определена')
        category = await self.session.get(tables.Category, category_id)
        config = (category.value or {}).get('fsm') if category else None
        if not config:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail='категория объекта не определяет машину состояний (value.fsm)')
        return config

    async def _current_row(self, table: str, objectid: uuid.UUID) -> tables.Property | None:
        q = select(tables.Property).where(
            tables.Property.table == table,
            tables.Property.objectid == objectid,
            tables.Property.code == STATE_CODE)
        return (await self.session.execute(q)).scalars().first()

    @staticmethod
    def _machine(config: dict, table: str, objectid: uuid.UUID,
                 row: tables.Property | None) -> FSMMixin:
        machine = _machine_class(config)()
        machine.table, machine.objectid = table, objectid
        if row is not None:
            machine._set_state(row.value['state'])
        return machine
