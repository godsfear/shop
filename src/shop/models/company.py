import datetime
import uuid

from pydantic import BaseModel

from .base import CreatorMixin, ReadMixin


class CompanyBase(BaseModel):
    category: uuid.UUID | None = None
    code: str
    name: str | None = None
    country: uuid.UUID
    registered: datetime.date
    closed: datetime.date | None = None


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(BaseModel):
    category: uuid.UUID | None = None
    code: str | None = None
    name: str | None = None
    country: uuid.UUID | None = None
    registered: datetime.date | None = None
    closed: datetime.date | None = None


class CompanyFilter(BaseModel):
    category: uuid.UUID | None = None
    country: uuid.UUID | None = None
    code: str | None = None
    name: str | None = None


class Company(CompanyBase, ReadMixin, CreatorMixin):
    pass
