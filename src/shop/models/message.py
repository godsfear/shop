import datetime
import uuid
from pydantic import BaseModel, ConfigDict


class MessageBase(BaseModel):
    category: uuid.UUID
    code: str
    author: uuid.UUID
    receiver: uuid.UUID
    name: str
    content: str
    description: str | None
    begins: datetime.datetime
    ends: datetime.datetime | None


class Message(MessageBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class MessageCreate(MessageBase):
    pass


class MessageUpdate(MessageBase):
    pass
