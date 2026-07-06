"""Проводки и балансы (вариант Б: производные данные считает консумер).

Operation пишется СИНХРОННО и в той же транзакции кладёт событие
'operation.created' в outbox — клиент сразу получает проводку, а Balance
пересчитывает консумер (exactly-once в пределах БД, см. outbox.py).
Balance ведётся через versioned_update: история балансов — копии-версии.

Суммы двух сторон раздельные: amount_db в валюте дебет-счёта (списание),
amount_cr — в валюте кредит-счёта (зачисление). В одной валюте суммы обязаны
совпадать; кросс-валютная проводка требует обе суммы — применённый курс
фиксируется самими суммами, справочник курсов — таблица Rate.
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
        rows = (await self.session.execute(
            select(tables.Account.id, tables.Account.currency)
            .where(tables.Account.id.in_((data.debit, data.credit))))).all()
        currencies = {row[0]: row[1] for row in rows}
        for side, account_id in (('debit', data.debit), ('credit', data.credit)):
            if account_id not in currencies:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                    detail=f'счёт {side} не найден')
        if currencies[data.debit] == currencies[data.credit]:
            # одна валюта: суммы сторон обязаны совпадать
            if data.amount_cr is not None and data.amount_cr != data.amount_db:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail='счета в одной валюте: amount_cr должен '
                                           'совпадать с amount_db (или не указываться)')
            amount_cr = data.amount_db
        else:
            # кросс-валютная: сумма в валюте кредита обязательна (курс фиксирует
            # вызывающий; сверка со справочником Rate — на его стороне)
            if data.amount_cr is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail='кросс-валютная проводка: укажите amount_cr — '
                                           'сумму в валюте кредит-счёта')
            amount_cr = data.amount_cr
        operation = tables.Operation(**data.model_dump(exclude={'amount_cr'}),
                                     amount_cr=amount_cr, creator=creator)
        self.session.add(operation)
        await self.session.flush()
        emit(self.session, TOPIC_OPERATION_CREATED, {
            'operation': str(operation.id),
            'debit': str(operation.debit),
            'credit': str(operation.credit),
            'amount_db': str(operation.amount_db),
            'amount_cr': str(operation.amount_cr),
        })
        await self.session.commit()  # проводка и событие — одна транзакция
        return operation

    async def balance(self, account_id: uuid.UUID) -> Decimal:
        """Текущий баланс счёта (0, если проводок ещё не было)."""
        exists = (await self.session.execute(
            select(tables.Account.id).where(tables.Account.id == account_id))
        ).scalar_one_or_none()
        if exists is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='счёт не найден')
        value = (await self.session.execute(
            select(tables.Balance.value).where(tables.Balance.account == account_id))
        ).scalar_one_or_none()
        return value if value is not None else Decimal(0)


@outbox_handler(TOPIC_OPERATION_CREATED)
async def _apply_operation(session: AsyncSession, payload: dict) -> None:
    """Консумер: пересчёт балансов обеих сторон проводки.

    Счета блокируются в детерминированном порядке (по id) — конкурентные
    события по пересекающимся счетам не взаимоблокируются. Balance правится
    через versioned_update: история значений остаётся копиями-версиями.
    """
    deltas = sorted([(uuid.UUID(payload['debit']), -Decimal(payload['amount_db'])),
                     (uuid.UUID(payload['credit']), Decimal(payload['amount_cr']))])
    for account_id, delta in deltas:
        row = (await session.execute(
            select(tables.Balance)
            .where(tables.Balance.account == account_id)
            .with_for_update())).scalar_one_or_none()
        if row is None:
            # гонка первичного создания: два консумера могут одновременно не найти
            # строку — uq_balance_account отвергнет второго, retry outbox дочитает
            session.add(tables.Balance(account=account_id, value=delta))
        else:
            await versioned_update(session, tables.Balance, row.id,
                                   {'value': row.value + delta})
    # commit выполняет process_one — вместе с пометкой события
