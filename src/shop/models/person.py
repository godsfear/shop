import datetime
import uuid

from pydantic import BaseModel

from .base import ReadMixin


class PersonBase(BaseModel):
    name: dict                    # {'last': ..., 'first': ..., 'middle': ...}
    sex: bool
    birthdate: datetime.date
    birth_place: uuid.UUID | None = None   # необязательно (самоучёт-регистрация)


class PersonCreate(PersonBase):
    pass


class PersonUpdate(BaseModel):
    name: dict | None = None
    sex: bool | None = None
    birthdate: datetime.date | None = None
    birth_place: uuid.UUID | None = None


class Person(PersonBase, ReadMixin):
    pass
