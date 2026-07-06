from fastapi import APIRouter
from .entity import router as entity_router
from .user import router as user_router
from .auth import router as auth_router
from .category import router as category_router
from .currency import router as currency_router
from .country import router as country_router
from .bridge import router as bridge_router
from .fsm import router as fsm_router
from .operation import router as operation_router
from .person import router as person_router
from .place import router as place_router
from .rate import router as rate_router
from ..settings import settings

router = APIRouter(prefix=settings.api_prefix, tags=['api'])
router.include_router(auth_router)
router.include_router(entity_router)
router.include_router(user_router)
router.include_router(category_router)
router.include_router(currency_router)
router.include_router(country_router)
router.include_router(fsm_router)
router.include_router(operation_router)
router.include_router(person_router)
router.include_router(place_router)
router.include_router(rate_router)
router.include_router(bridge_router)
