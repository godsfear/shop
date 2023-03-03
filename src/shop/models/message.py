import datetime
import uuid
from pydantic import BaseModel


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
    id: uuid.UUID

    class Config:
        orm_mode = True


class MessageCreate(MessageBase):
    pass


class MessageUpdate(MessageBase):
    pass
