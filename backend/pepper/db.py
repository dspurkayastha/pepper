"""Async SQLAlchemy engine and session factory.

SQLite (aiosqlite) by default; any SQLAlchemy async URL works, e.g.
postgresql+asyncpg://... once the deployment moves to Postgres.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def configure(url: str) -> None:
    global _engine, _sessionmaker
    _engine = create_async_engine(url)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)


async def create_all() -> None:
    from pepper import models  # noqa: F401  (register tables)

    assert _engine is not None, "db.configure() not called"
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose() -> None:
    if _engine is not None:
        await _engine.dispose()


def sessionmaker() -> async_sessionmaker[AsyncSession]:
    assert _sessionmaker is not None, "db.configure() not called"
    return _sessionmaker


async def get_db() -> AsyncIterator[AsyncSession]:
    async with sessionmaker()() as session:
        yield session
