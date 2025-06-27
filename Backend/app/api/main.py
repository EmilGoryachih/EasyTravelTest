from fastapi import APIRouter

from app.api.routes import UserRout
from app.api.routes import TokenRout
from app.api.routes import POIRouter

api_router = APIRouter()

api_router.include_router(UserRout.router, prefix="/user", tags=["user"])
api_router.include_router(TokenRout.router, prefix="/token", tags=["token"])
api_router.include_router(POIRouter.router, prefix="/poi", tags=["poi"])