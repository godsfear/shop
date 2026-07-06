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
    amount: Decimal = Field(gt=0)
    description: str | None = None


class OperationCreate(OperationBase):
    pass


class Operation(OperationBase, ReadMixin, CreatorMixin):
    pass


class Balance(BaseModel):
    account: uuid.UUID
    value: Decimal
