import datetime
import uuid
from pydantic import BaseModel, ConfigDict


class AccountBase(BaseModel):
    category: uuid.UUID
    code: str
    currency: uuid.UUID
    issuer: uuid.UUID
    issuer_table: str
    name: str
    description: str | None
    begins: datetime.datetime
    ends: datetime.datetime | None
    author: uuid.UUID


class Account(AccountBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class AccountCreate(AccountBase):
    pass


class AccountUpdate(AccountBase):
    pass
