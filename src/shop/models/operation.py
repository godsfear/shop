import uuid
from decimal import Decimal

from pydantic import BaseModel, Field

from .base import CreatorMixin, ReadMixin


class OperationBase(BaseModel):
    category: uuid.UUID | None = None
    code: str
    number: str
    debit: uuid.UUID
    credit: uuid.UUID
    amount_db: Decimal = Field(gt=0)   # сумма в валюте дебет-счёта
    description: str | None = None


class OperationCreate(OperationBase):
    # в одной валюте можно не указывать (= amount_db); для кросс-валютной — обязательна
    amount_cr: Decimal | None = Field(default=None, gt=0)


class Operation(OperationBase, ReadMixin, CreatorMixin):
    amount_cr: Decimal                 # сумма в валюте кредит-счёта


class Balance(BaseModel):
    account: uuid.UUID
    value: Decimal
