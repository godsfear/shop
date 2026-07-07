from typing import List

from fastapi import HTTPException, status
from sqlalchemy import select, func

from shop.tables import Country
from shop.models import CountryFilter
from shop.models import Country as CountryModel
from .crud import CachedCrudService


class CountryService(CachedCrudService):
    table = Country
    ns = 'country'
    read_model = CountryModel

    async def get_all(self) -> List[Country]:
        async def load():
            res = await self.session.execute(select(Country))
            return list(res.scalars().all())

        return await self._cached_list('all', load)

    async def find(self, flt: CountryFilter) -> Country:
        conditions = []
        if flt.iso2 is not None:
            conditions.append(func.lower(Country.iso2) == flt.iso2.lower())
        if flt.iso3 is not None:
            conditions.append(func.lower(Country.iso3) == flt.iso3.lower())
        if flt.m49 is not None:
            conditions.append(Country.m49 == flt.m49)
        if flt.name is not None:
            conditions.append(func.lower(Country.name) == flt.name.lower())
        if not conditions:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Пустой фильтр')

        async def load():
            res = await self.session.execute(select(Country).where(*conditions))
            country = res.scalar_one_or_none()
            if country is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
            return country

        return await self._cached_one(f'find:{flt.model_dump_json()}', load)
