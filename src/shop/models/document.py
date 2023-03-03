import datetime
import uuid
from pydantic import BaseModel


class DocumentBase(BaseModel):
    category: uuid.UUID
    code: str
    country: uuid.UUID
    name: str
    issuer_table: str
    issuer: uuid.UUID
    series: str
    number: str
    description: str | None
    issue: datetime.date
    expire: datetime.date
    begins: datetime.datetime
    ends: datetime.datetime | None


class Document(DocumentBase):
    id: uuid.UUID

    class Config:
        orm_mode = True


class DocumentCreate(DocumentBase):
    pass


class DocumentUpdate(DocumentBase):
    pass
