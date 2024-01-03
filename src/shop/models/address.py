import datetime
import uuid
from pydantic import BaseModel, ConfigDict


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
    author: uuid.UUID


class Address(AddressBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class AddressCreate(AddressBase):
    pass


class AddressUpdate(AddressBase):
    pass
