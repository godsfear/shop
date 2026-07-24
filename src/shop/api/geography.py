from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query

from ..models.geography import GeographyOption
from ..services.geography import GeographyService
from ..services.translation import primary_language


router = APIRouter(prefix="/geography", tags=["geography"])


@router.get("/countries", response_model=list[GeographyOption])
async def countries(
    service: Annotated[GeographyService, Depends(GeographyService)],
    accept_language: Annotated[str | None, Header()] = None,
):
    return await service.countries(primary_language(accept_language))


@router.get("/cities", response_model=list[GeographyOption])
async def cities(
    service: Annotated[GeographyService, Depends(GeographyService)],
    country: Annotated[str, Query(min_length=2, max_length=2)],
    accept_language: Annotated[str | None, Header()] = None,
):
    return await service.cities(country, primary_language(accept_language))
