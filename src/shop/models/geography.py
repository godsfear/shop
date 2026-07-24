import uuid

from pydantic import BaseModel


class GeographyOption(BaseModel):
    id: uuid.UUID
    code: str
    name: str
