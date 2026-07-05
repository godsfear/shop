import uuid
from decimal import Decimal

from pydantic import BaseModel

from .base import CreatorMixin, ReadMixin


class CurrencyBase(BaseModel):
    category: uuid.UUID
    code: str
    name: str
    num: int | None = None
    adjective: str
    name_plural: str
    name_minor: str
    name_minor_plural: str
    symbol: str
    symbol_native: str
    decimals: int = 2
    rounding: Decimal = Decimal("0")
    description: str | None = None


class CurrencyCreate(CurrencyBase):
    pass


class CurrencyUpdate(BaseModel):
    category: uuid.UUID | None = None
    code: str | None = None
    name: str | None = None
    num: int | None = None
    adjective: str | None = None
    name_plural: str | None = None
    name_minor: str | None = None
    name_minor_plural: str | None = None
    symbol: str | None = None
    symbol_native: str | None = None
    decimals: int | None = None
    rounding: Decimal | None = None
    description: str | None = None


class CurrencyFilter(BaseModel):
    category: uuid.UUID | None = None
    code: str | None = None
    num: int | None = None


class Currency(CurrencyBase, ReadMixin, CreatorMixin):
    pass
