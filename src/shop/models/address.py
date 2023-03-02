import datetime
import uuid
from pydantic import BaseModel


class AddressBase(BaseModel):
    country: uuid.UUID
    region: uuid.UUID
    place: uuid.UUID
    postcode: str | None
    street: uuid.UUID
    building: str
    apartment: str
    begins: datetime.datetime
    ends: datetime.datetime | None


class Address(AddressBase):
    id: uuid.UUID

    class Config:
        orm_mode = True


class AddressCreate(AddressBase):
    pass


class AddressUpdate(AddressBase):
    pass
