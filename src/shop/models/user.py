import datetime
import uuid
from pydantic import BaseModel


class UserEditable(BaseModel):
    email: str | None
    phone: str | None


class UserCheck(BaseModel):
    checked: bool


class UserBase(UserEditable, UserCheck):
    person_id: uuid.UUID
    begins: datetime.datetime
    ends: datetime.datetime | None


class UserCreate(UserBase):
    password: str


class UserUpdate(UserEditable):
    password: str


class UserSave(UserEditable, UserCheck):
    passhash: str


class User(UserBase):
    id: uuid.UUID

    class Config:
        orm_mode = True
