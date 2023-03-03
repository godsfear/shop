import datetime
import uuid
from pydantic import BaseModel


class CompanyBase(BaseModel):
    country: uuid.UUID
    code: str
    name: str
    description: str | None
    begins: datetime.datetime
    ends: datetime.datetime | None
    author: uuid.UUID


class Company(CompanyBase):
    id: uuid.UUID

    class Config:
        orm_mode = True


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(CompanyBase):
    pass
