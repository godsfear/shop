from fastapi import APIRouter
from .entity import router as entity_router
from .user import router as user_router
from .auth import router as auth_router
from .person import router as person_router
from .property import router as property_router
from .category import router as category_router
from .currency import router as currency_router
from .company import router as company_router
from .country import router as country_router
from .place import router as place_router
from ..settings import settings

router = APIRouter(prefix=settings.api_prefix, tags=['api'])
router.include_router(auth_router)
router.include_router(entity_router)
router.include_router(user_router)
router.include_router(person_router)
router.include_router(property_router)
router.include_router(category_router)
router.include_router(currency_router)
router.include_router(company_router)
router.include_router(country_router)
router.include_router(place_router)
