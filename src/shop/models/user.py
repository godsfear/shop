import datetime
import uuid
from pydantic import BaseModel, ConfigDict


class UserEditable(BaseModel):
    email: str | None = None
    phone: str | None = None


class UserBase(UserEditable):
    person_id: uuid.UUID


class UserCreate(UserBase):
    password: str


class UserUpdate(UserEditable):
    checked: bool
    password: str
    ends: datetime.datetime | None = None


class UserSave(UserBase):
    passhash: str


class User(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    begins: datetime.datetime
