import uuid
from decimal import Decimal

from pydantic import BaseModel, Field

from .base import CreatorMixin, ReadMixin


class RateBase(BaseModel):
    category: uuid.UUID | None = None
    code: str                      # источник/тип курса: cbr, internal, ...
    currency_from: uuid.UUID
    currency_to: uuid.UUID
    value: Decimal = Field(gt=0)   # сколько currency_to за единицу currency_from
    description: str | None = None


class RateCreate(RateBase):
    pass


class RateUpdate(BaseModel):
    category: uuid.UUID | None = None
    code: str | None = None
    currency_from: uuid.UUID | None = None
    currency_to: uuid.UUID | None = None
    value: Decimal | None = Field(default=None, gt=0)
    description: str | None = None


class RateFilter(BaseModel):
    category: uuid.UUID | None = None
    code: str | None = None
    currency_from: uuid.UUID | None = None
    currency_to: uuid.UUID | None = None


class Rate(RateBase, ReadMixin, CreatorMixin):
    pass
