import datetime
import uuid
from pydantic import BaseModel


class CurrencyBase(BaseModel):
    category: uuid.UUID
    code: str
    numcode: int


class CurrencyUpdate(CurrencyBase):
    name: str
    name_plural: str
    symbol: str
    symbol_native: str
    decimal_digits: int
    rounding: float
    description: str | None
    begins: datetime.datetime
    ends: datetime.datetime | None
    author: uuid.UUID


class Currency(CurrencyUpdate):
    id: uuid.UUID

    class Config:
        orm_mode = True


class CurrencyCreate(CurrencyUpdate):
    pass
