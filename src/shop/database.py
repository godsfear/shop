from typing import AsyncGenerator, Any
from asyncio import current_task
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, async_scoped_session
from .settings import settings


class DatabaseHelper:
    def __init__(self, url: str, echo: bool = False):
        # ponytail: NullPool — свежее соединение на сессию. Дефолтный async-пул
        # при частом открытии/закрытии сессий (outbox_worker дренит в цикле)
        # возвращал соединение с открытой транзакцией, удерживая FOR UPDATE и
        # пряча событие под SKIP LOCKED навсегда. Ценой одного connect на сессию
        # снимаем целый класс утечек состояния. Потолок: если connect-оверхед
        # станет заметен — внешний пулер (PgBouncer) + NullPool на стороне app.
        self.engine = create_async_engine(
            url=url,
            echo=echo,
            poolclass=NullPool,
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

    async def session_dependency(self) -> AsyncGenerator[AsyncSession, Any]:
        async with self.session_factory() as session:  # закрывает и при исключении
            yield session

    async def scoped_session_dependency(self) -> AsyncGenerator[async_scoped_session[AsyncSession], Any]:
        session = self.get_scoped_session()
        try:
            yield session
        finally:
            # finally ОБЯЗАТЕЛЕН: оборванный клиентом запрос (или исключение
            # хэндлера) иначе пропускает close -> соединение остаётся
            # 'idle in transaction' и его FOR UPDATE-замки висят вечно,
            # подвешивая все последующие записи тех же строк
            await session.remove()


db_helper = DatabaseHelper(
    url=settings.database_uri,
    echo=settings.sql_echo,
)
