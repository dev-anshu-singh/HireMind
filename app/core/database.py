from typing import AsyncGenerator, Generator
from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# --- Synchronous Engine (Used by Alembic migrations & CLI scripts) ---
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.DATABASE_URL,
    echo=(settings.ENVIRONMENT == "development"),
    connect_args=connect_args,
    pool_pre_ping=True,
)


def init_db() -> None:
    """Create all database tables using SQLModel metadata (sync)."""
    import app.models  # noqa: F401
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    """Synchronous database session dependency."""
    with Session(engine) as session:
        yield session


# --- Asynchronous Engine (Used by FastAPI async routes) ---
async_connect_args = {}
if settings.async_database_url.startswith("sqlite"):
    async_connect_args["check_same_thread"] = False

async_engine = create_async_engine(
    settings.async_database_url,
    echo=(settings.ENVIRONMENT == "development"),
    connect_args=async_connect_args,
    pool_pre_ping=True,
)

async_session_maker = sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Asynchronous database session dependency for FastAPI async routes."""
    async with async_session_maker() as session:
        yield session
