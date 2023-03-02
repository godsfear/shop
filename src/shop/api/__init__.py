from fastapi import APIRouter
from .entity import router as entity_router
from .user import router as user_router
from .auth import router as auth_router
from .person import router as person_router
from .property import router as property_router
from .property import router as category_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(entity_router)
router.include_router(user_router)
router.include_router(person_router)
router.include_router(property_router)
router.include_router(category_router)
