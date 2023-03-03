import datetime
import uuid
from pydantic import BaseModel


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


class Operation(OperationBase):
    id: uuid.UUID

    class Config:
        orm_mode = True


class OperationCreate(OperationBase):
    pass


class OperationUpdate(OperationBase):
    pass
