import datetime
import uuid
from pydantic import BaseModel


class UserBase(BaseModel):
    email: str | None
    phone: str | None
    person_id: uuid.UUID
    checked: bool
    begins: datetime.datetime
    ends: datetime.datetime | None


class UserEditable(BaseModel):
    email: str | None
    phone: str | None


class UserCreate(UserBase):
    password: str


class UserUpdate(UserEditable):
    password: str


class UserSave(UserEditable):
    passhash: str
    checked: bool


class User(UserBase):
    id: uuid.UUID

    class Config:
        orm_mode = True
