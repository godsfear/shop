import datetime
import uuid
from pydantic import BaseModel


class CountryBase(BaseModel):
    code: str
    name: str
    currency: uuid.UUID
    description: str | None
    begins: datetime.datetime
    ends: datetime.datetime | None
    author: uuid.UUID


class Country(CountryBase):
    id: uuid.UUID

    class Config:
        orm_mode = True


class CountryCreate(CountryBase):
    pass


class CountryUpdate(CountryBase):
    pass
