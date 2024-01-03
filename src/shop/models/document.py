import datetime
import uuid
from pydantic import BaseModel, ConfigDict


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
    author: uuid.UUID


class Document(DocumentBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class DocumentCreate(DocumentBase):
    pass


class DocumentUpdate(DocumentBase):
    pass
