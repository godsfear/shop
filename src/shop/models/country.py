import datetime
import uuid
from pydantic import BaseModel


class CountryBase(BaseModel):
    code: str
    name: str
    author: uuid.UUID
    currency: uuid.UUID | None = None
    description: str | None = None
    ends: datetime.datetime | None = None


class CountryUpdate(CountryBase):
    pass


class CountryCreate(CountryBase):
    pass


class Country(CountryUpdate):
    id: uuid.UUID
    begins: datetime.datetime

    class Config:
        orm_mode = True
