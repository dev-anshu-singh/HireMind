from fastapi import FastAPI, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.config import settings
from app.core.database import get_async_session
from app.api.v1.router import api_v1_router

# Initialize FastAPI Application
app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Set up CORS middleware for Web Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API v1 routes
app.include_router(api_v1_router, prefix=settings.API_V1_STR)


@app.get("/health", status_code=status.HTTP_200_OK, tags=["Health"])
async def health_check(db: AsyncSession = Depends(get_async_session)):
    """
    Health check endpoint to verify API server and Neon PostgreSQL connectivity.
    """
    try:
        # Execute lightweight ping query to verify database connection
        await db.execute(text("SELECT 1"))
        return {
            "status": "healthy",
            "environment": settings.ENVIRONMENT,
            "database": "connected (Neon Postgres)",
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database_error": str(e),
        }
