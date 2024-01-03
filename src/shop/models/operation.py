import datetime
import uuid
from pydantic import BaseModel, ConfigDict


class OperationBase(BaseModel):
    category: uuid.UUID
    code: str
    debit: uuid.UUID
    credit: uuid.UUID
    number: str
    amount: float
    description: str | None
    begins: datetime.datetime
    ends: datetime.datetime | None
    author: uuid.UUID


class Operation(OperationBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class OperationCreate(OperationBase):
    pass


class OperationUpdate(OperationBase):
    pass
