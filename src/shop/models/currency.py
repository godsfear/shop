import datetime
import uuid
from pydantic import BaseModel


class CurrencyBase(BaseModel):
    category: uuid.UUID
    code: str
    name: str
    description: str | None
    begins: datetime.datetime
    ends: datetime.datetime | None


class Currency(CurrencyBase):
    id: uuid.UUID

    class Config:
        orm_mode = True


class CurrencyCreate(CurrencyBase):
    pass


class CurrencyUpdate(CurrencyBase):
    pass
