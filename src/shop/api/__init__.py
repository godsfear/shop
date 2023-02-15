from fastapi import APIRouter
from .entity import router as product_router

router = APIRouter()
router.include_router(product_router)
