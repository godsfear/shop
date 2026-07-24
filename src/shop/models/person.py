import datetime
import uuid

from pydantic import BaseModel

from .base import ReadMixin


class PersonBase(BaseModel):
    name: dict                    # {'last': ..., 'first': ..., 'middle': ...}
    sex: bool
    birthdate: datetime.date
    birth_place: uuid.UUID | None = None   # необязательно (самоучёт-регистрация)
    # Подписи нужны ИИ, стабильные коды — повторному выбору локализованных справочников.
    residence: dict | None = None          # {country, city, country_code?, city_code?}


class PersonCreate(PersonBase):
    pass


class PersonUpdate(BaseModel):
    name: dict | None = None
    sex: bool | None = None
    birthdate: datetime.date | None = None
    birth_place: uuid.UUID | None = None
    residence: dict | None = None


class Person(PersonBase, ReadMixin):
    pass
