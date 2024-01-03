import datetime
import uuid
from pydantic import BaseModel, ConfigDict


class CompanyBase(BaseModel):
    country: uuid.UUID
    code: str
    name: str
    description: str | None
    begins: datetime.datetime
    ends: datetime.datetime | None
    author: uuid.UUID


class Company(CompanyBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(CompanyBase):
    pass
