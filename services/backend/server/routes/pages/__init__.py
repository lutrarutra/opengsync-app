from fastapi import APIRouter

from . import dashboard, login

router = APIRouter()
router.include_router(dashboard.router)
router.include_router(login.router)