import uuid
from typing import List

from fastapi import APIRouter, Depends, Query

from ..models.auth import TokenPayload
from ..models.translation import SearchHit, Translation, TranslationSearch, TranslationSet
from ..services.auth import require_admin
from ..services.translation import TranslationService

router = APIRouter(prefix='/translation', tags=['translation'])


@router.post('/search', response_model=List[SearchHit])
async def search_translations(params: TranslationSearch,
                              service: TranslationService = Depends()):
    """Поиск объектов по переводу на локали (товары, услуги, категории...)."""
    return await service.search(params)


@router.get('/{table}/{objectid}', response_model=dict[str, str])
async def get_translations(table: str, objectid: uuid.UUID,
                           locale: str = Query(min_length=2, max_length=8),
                           service: TranslationService = Depends()):
    """Переводы объекта на локаль: {поле: перевод}; фолбэк на базовое поле — у клиента."""
    return await service.get_translations(table, objectid, locale)


@router.put('/{table}/{objectid}', response_model=List[Translation])
async def set_translations(table: str, objectid: uuid.UUID, items: List[TranslationSet],
                           service: TranslationService = Depends(),
                           payload: TokenPayload = Depends(require_admin)):
    return await service.set_translations(table, objectid, items)
