import datetime
import uuid
from pydantic import BaseModel, ConfigDict


class CountryBase(BaseModel):
    iso2: str
    iso3: str
    m49: int
    name: str


class CountryGet(CountryBase):
    iso2: str | None = None
    iso3: str | None = None
    m49: int | None = None
    name: str | None = None


class CountryUpdate(BaseModel):
    author: uuid.UUID | None = None
    description: str | None = None
    ends: datetime.datetime | None = None


class CountryCreate(CountryBase, CountryUpdate):
    pass


class Country(CountryCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    begins: datetime.datetime
