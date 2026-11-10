from collections.abc import Generator

from anyio import CapacityLimiter
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from starlette.requests import Request

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url, pool_pre_ping=True,
    pool_size=settings.database_pool_size, max_overflow=settings.database_max_overflow,
    pool_timeout=30, pool_recycle=300,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


# Importar el paquete de modelos aquí (después de definir Base, antes de que
# nadie use Base.metadata) es lo que registra todas las tablas para
# Base.metadata.create_all (tests) y para Alembic autogenerate. Sin esto,
# un modelo nuevo que ningún repository/service importe todavía quedaría
# invisible para create_all/migraciones.
from app.models import *  # noqa: E402,F401


def get_database_capacity(request: Request) -> CapacityLimiter:
    """Admit DB work asynchronously, at the existing engine pool capacity.

    The limiter lives on this ASGI app, not in user/session state. Request
    dependencies and the protected-edit middleware share the same budget.
    """
    limiter = getattr(request.app.state, "database_capacity", None)
    if limiter is None:
        limiter = CapacityLimiter(settings.database_pool_size + settings.database_max_overflow)
        request.app.state.database_capacity = limiter
    return limiter


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
