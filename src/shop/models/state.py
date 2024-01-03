import datetime
import uuid
from pydantic import BaseModel, ConfigDict


class StateBase(BaseModel):
    category: uuid.UUID
    code: str
    name: str
    description: str | None
    begins: datetime.datetime
    ends: datetime.datetime | None
    author: uuid.UUID


class State(StateBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class StateCreate(StateBase):
    pass


class StateUpdate(StateBase):
    pass
