"""Компании — identity-домен.

Создатель компании автоматически становится её первым управляющим
(manage-consent), той же транзакцией: у только что созданной компании
нет ни владельца-пользователя, ни другого управляющего, поэтому право
управлять её доступами должен получить тот, кто её завёл.
"""
import uuid
from typing import List

from sqlalchemy import func

from .. import tables
from ..models.company import CompanyCreate, CompanyFilter
from .consent import ConsentService
from .crud import CrudService


class CompanyService(CrudService):
    table = tables.Company

    async def create(self, data: CompanyCreate, creator: uuid.UUID | None = None):
        company = tables.Company(**data.model_dump(), creator=creator)
        self.session.add(company)
        await self.session.flush()  # нужен company.id для manage-гранта
        if creator is not None:
            await ConsentService(session=self.session).bootstrap_manage(
                'company', company.id, creator, reason='создатель компании')
        await self.session.commit()
        return company

    async def find(self, flt: CompanyFilter) -> List[tables.Company]:
        conditions = []
        if flt.category is not None:
            conditions.append(tables.Company.category == flt.category)
        if flt.country is not None:
            conditions.append(tables.Company.country == flt.country)
        if flt.code is not None:
            conditions.append(tables.Company.code == flt.code)
        if flt.name is not None:
            conditions.append(func.lower(tables.Company.name) == flt.name.lower())
        return await self._where(conditions)
