import uuid
import datetime
from pydantic import BaseModel, ConfigDict


class PersonBase(BaseModel):
    name_first: str
    name_last: str
    name_third: str
    sex: bool
    birthdate: datetime.date
    birth_place: uuid.UUID | None = None


class Person(PersonBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    begins: datetime.datetime


class PersonCreate(PersonBase):
    pass


class PersonUpdate(PersonBase):
    ends: datetime.datetime | None = None
