from fastapi import APIRouter
from app.api.v1.campaigns import router as campaigns_router

api_v1_router = APIRouter()

# Include feature routers
api_v1_router.include_router(campaigns_router)
