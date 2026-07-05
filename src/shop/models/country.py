from pydantic import BaseModel, Field

from .base import CreatorMixin, ReadMixin


class CountryBase(BaseModel):
    iso2: str = Field(min_length=2, max_length=2)
    iso3: str = Field(min_length=3, max_length=3)
    m49: int | None = Field(default=None, ge=0, le=999)
    name: str
    description: str | None = None


class CountryCreate(CountryBase):
    pass


class CountryUpdate(BaseModel):
    iso2: str | None = Field(default=None, min_length=2, max_length=2)
    iso3: str | None = Field(default=None, min_length=3, max_length=3)
    m49: int | None = Field(default=None, ge=0, le=999)
    name: str | None = None
    description: str | None = None


class CountryFilter(BaseModel):
    iso2: str | None = None
    iso3: str | None = None
    m49: int | None = None
    name: str | None = None


class Country(CountryBase, ReadMixin, CreatorMixin):
    pass
