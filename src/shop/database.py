from typing import Generator
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from .settings import settings
from fastapi import HTTPException, status

engine = create_async_engine(
    settings.database_uri,
    future=True,
    echo=True,
)

Session = sessionmaker(
    engine,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
    class_=AsyncSession
)


async def get_session() -> Generator:
    session: AsyncSession | None = None
    try:
        session = Session()
        yield session
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Database session create error: {str(e)}'
        )
    finally:
        await session.close()
