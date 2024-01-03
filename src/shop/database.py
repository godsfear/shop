from typing import Generator, Dict
from asyncio import current_task
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, async_scoped_session
from .settings import settings
from fastapi import HTTPException, status
import uuid
import datetime

# engine = create_async_engine(
#     settings.database_uri,
#     future=True,
#     echo=True,
# )
#
# Session = sessionmaker(
#     engine,
#     expire_on_commit=False,
#     autocommit=False,
#     autoflush=False,
#     class_=AsyncSession
# )
#
#
# async def get_session() -> Generator:
#     session: AsyncSession | None = None
#     try:
#         session = Session()
#         yield session
#         await session.commit()
#     except Exception as e:
#         await session.rollback()
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail=f'Database session create error: {str(e)}'
#         )
#     finally:
#         await session.close()


def serialize2str(_dict: Dict) -> Dict:
    for key, value in _dict.items():
        if isinstance(value, (uuid.UUID, datetime.datetime)):
            _dict[key] = str(value)
    return _dict


class DatabaseHelper:
    def __init__(self, url: str, echo: bool = False):
        self.engine = create_async_engine(
            url=url,
            echo=echo,
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )

    def get_scoped_session(self):
        session = async_scoped_session(
            session_factory=self.session_factory,
            scopefunc=current_task,
        )
        return session

    async def session_dependency(self) -> AsyncSession:
        async with self.session_factory() as session:
            yield session
            await session.close()

    async def scoped_session_dependency(self) -> AsyncSession:
        session = self.get_scoped_session()
        yield session
        await session.close()


db_helper = DatabaseHelper(
    url=settings.database_uri,
    echo=settings.sql_echo,
)
