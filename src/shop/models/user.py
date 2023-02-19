import uuid
from pydantic import BaseModel


class BaseUser(BaseModel):
    username: str
    person_id: uuid.UUID


class UserCreate(BaseUser):
    password: str


class UserUpdate(BaseUser):
    password: str


class UserSave(BaseUser):
    passhash: str


class User(BaseUser):
    id: uuid.UUID

    class Config:
        orm_mode = True
