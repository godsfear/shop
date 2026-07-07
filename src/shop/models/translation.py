import uuid

from pydantic import BaseModel, Field

from .base import ReadMixin


class TranslationSet(BaseModel):
    """Upsert перевода одного поля: язык указывается ISO-кодом локали."""
    language: str = Field(min_length=2, max_length=8)   # iso: ru, de, en-US
    field: str = 'name'
    content: str = Field(min_length=1)


class Translation(ReadMixin):
    table: str
    objectid: uuid.UUID
    language: uuid.UUID
    field: str
    content: str


class TranslationSearch(BaseModel):
    q: str = Field(min_length=2)
    locale: str = Field(min_length=2, max_length=8)
    field: str = 'name'
    table: str | None = None
    limit: int = Field(default=50, ge=1, le=100)


class SearchHit(BaseModel):
    """Найденный перевод: полиморфная ссылка на объект + совпавший текст."""
    table: str
    objectid: uuid.UUID
    content: str
