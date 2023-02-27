import datetime
import uuid
from pydantic import BaseModel


class StateBase(BaseModel):
    category: uuid.UUID
    code: str
    name: str
    description: str | None
    begins: datetime.datetime
    ends: datetime.datetime


class State(StateBase):
    id: uuid.UUID

    class Config:
        orm_mode = True


class StateCreate(StateBase):
    pass


class StateUpdate(StateBase):
    pass
