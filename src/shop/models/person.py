import uuid
from datetime import datetime
from pydantic import BaseModel


class PersonBase(BaseModel):
    name_first: str
    name_last: str
    name_third: str
    birthdate: datetime.date
    birth_place: uuid.UUID


class Person(PersonBase):
    id: uuid.UUID

    class Config:
        orm_mode = True


class PersonCreate(PersonBase):
    pass


class PersonUpdate(PersonBase):
    pass
