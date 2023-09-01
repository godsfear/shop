import datetime
import uuid
from pydantic import BaseModel


class CurrencyBase(BaseModel):
    category: uuid.UUID


class CurrencyUpdate(CurrencyBase):
    code: str
    num: int | None = None
    name: str | None = None
    name_plural: str | None = None
    name_minor: str | None = None
    name_minor_plural: str | None = None
    adjective: str | None = None
    symbol: str | None = None
    symbol_native: str | None = None
    decimals: int | None = None
    rounding: float | None = None
    description: str | None = None
    ends: datetime.datetime | None = None
    author: uuid.UUID | None = None


class Currency(CurrencyUpdate):
    id: uuid.UUID
    begins: datetime.datetime

    class Config:
        orm_mode = True


class CurrencyCreate(CurrencyUpdate):
    pass
