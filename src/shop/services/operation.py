"""Проводки и балансы (вариант Б: производные данные считает консумер).

Operation пишется СИНХРОННО и в той же транзакции кладёт событие
'operation.created' в outbox — клиент сразу получает проводку, а Balance
пересчитывает консумер (exactly-once в пределах БД, см. outbox.py).
Balance ведётся через versioned_update: история балансов — копии-версии.

Упрощения каркаса: debit-счёт уменьшается, credit-счёт увеличивается на
amount; обе стороны обязаны быть в одной валюте (кросс-валютные проводки —
позже, с курсом и двумя суммами).
"""
import uuid
from decimal import Decimal

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import db_helper
from ..outbox import emit, outbox_handler
from ..versioning import versioned_update
from .. import tables
from ..models.operation import OperationCreate

TOPIC_OPERATION_CREATED = 'operation.created'


class OperationService:
    def __init__(self, session: AsyncSession = Depends(db_helper.scoped_session_dependency)):
        self.session = session

    async def create(self, data: OperationCreate,
                     creator: uuid.UUID | None = None) -> tables.Operation:
        if data.debit == data.credit:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail='дебет и кредит — один и тот же счёт')
        async with self.session as db:
            async with db.begin():
                currencies = {}
                for side, account_id in (('debit', data.debit), ('credit', data.credit)):
                    cur = (await db.execute(
                        select(tables.Account.currency)
                        .where(tables.Account.id == account_id))).scalar_one_or_none()
                    if cur is None:
                        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                            detail=f'счёт {side} не найден')
                    currencies[side] = cur
                if currencies['debit'] != currencies['credit']:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                        detail='счета в разных валютах — кросс-валютные '
                                               'проводки пока не поддерживаются')
                operation = tables.Operation(**data.model_dump(), creator=creator)
                db.add(operation)
                await db.flush()
                emit(db, TOPIC_OPERATION_CREATED, {
                    'operation': str(operation.id),
                    'debit': str(operation.debit),
                    'credit': str(operation.credit),
                    'amount': str(operation.amount),
                })
        return operation

    async def balance(self, account_id: uuid.UUID) -> Decimal:
        """Текущий баланс счёта (0, если проводок ещё не было)."""
        exists = (await self.session.execute(
            select(tables.Account.id).where(tables.Account.id == account_id))
        ).scalar_one_or_none()
        if exists is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='счёт не найден')
        value = (await self.session.execute(
            select(tables.Balance.value).where(tables.Balance.rate == account_id))
        ).scalar_one_or_none()
        return value if value is not None else Decimal(0)


@outbox_handler(TOPIC_OPERATION_CREATED)
async def _apply_operation(session: AsyncSession, payload: dict) -> None:
    """Консумер: пересчёт балансов обеих сторон проводки.

    Счета блокируются в детерминированном порядке (по id) — конкурентные
    события по пересекающимся счетам не взаимоблокируются. Balance правится
    через versioned_update: история значений остаётся копиями-версиями.
    """
    amount = Decimal(payload['amount'])
    deltas = sorted([(uuid.UUID(payload['debit']), -amount),
                     (uuid.UUID(payload['credit']), amount)])
    for account_id, delta in deltas:
        row = (await session.execute(
            select(tables.Balance)
            .where(tables.Balance.rate == account_id)
            .with_for_update())).scalar_one_or_none()
        if row is None:
            session.add(tables.Balance(rate=account_id, value=delta))
        else:
            await versioned_update(session, tables.Balance, row.id,
                                   {'value': row.value + delta})
    # commit выполняет process_one — вместе с пометкой события
