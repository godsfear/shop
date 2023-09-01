import datetime
import uuid
from pydantic import BaseModel


class CountryBase(BaseModel):
    iso2: str
    iso3: str
    m49: int
    name: str


class CountryUpdate(CountryBase):
    author: uuid.UUID | None = None
    description: str | None = None
    ends: datetime.datetime | None = None


class CountryCreate(CountryUpdate):
    pass


class Country(CountryUpdate):
    id: uuid.UUID
    begins: datetime.datetime

    class Config:
        orm_mode = True
