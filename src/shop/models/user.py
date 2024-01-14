import datetime
import uuid
from pydantic import BaseModel, ConfigDict


class UserBase(BaseModel):
    person_id: uuid.UUID


class UserCreate(UserBase):
    email: str | None = None
    phone: str | None = None
    password: str


class UserUpdate(UserBase):
    password: str
    email: str | None = None
    phone: str | None = None
    ends: datetime.datetime | None = None


class UserSave(UserBase):
    passhash: str


class UserValidate(UserBase):
    validated: bool


class User(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    begins: datetime.datetime
