import datetime
import uuid
from pydantic import BaseModel


class UserBase(BaseModel):
    username: str
    person_id: uuid.UUID
    begins: datetime.datetime
    ends: datetime.datetime | None


class UserCreate(UserBase):
    password: str


class UserUpdate(UserBase):
    password: str


class UserSave(UserBase):
    passhash: str


class User(UserBase):
    id: uuid.UUID

    class Config:
        orm_mode = True
