"""Redis-кэш с мягкой деградацией: кэш недоступен — работаем напрямую с БД.

Три паттерна использования (точки врезки):
- профиль пользователя (services/auth.get_current_user): ключ user:{id},
  инвалидация точечным delete при update/set_roles/expire;
- справочники (country/currency): версионирование пространства ключей —
  любая запись делает bump(ns), читатели включают версию в ключ, старые
  ключи умирают по TTL; точечная инвалидация не нужна;
- мост (bridge.resolve): сессионный кэш разрешённого псевдонима с коротким
  TTL, ключ включает actor — кэш не обходит ACL ключевого сервиса.

Ошибки соединения не роняют запрос: get -> None (промах), set/delete/bump ->
no-op, с одним предупреждением в лог на процесс.
"""
from functools import lru_cache
from typing import Any, Awaitable, Callable

import redis.asyncio as aioredis
from pydantic import TypeAdapter
from redis.exceptions import RedisError

from .logger import logger
from .settings import settings


class Cache:
    def __init__(self, url: str):
        self._redis = aioredis.from_url(url, decode_responses=True,
                                        socket_connect_timeout=1, socket_timeout=1)
        self._warned = False

    async def get(self, key: str) -> str | None:
        try:
            return await self._redis.get(key)
        except RedisError:
            self._warn()
            return None

    async def set(self, key: str, value: str, ttl_s: int) -> None:
        try:
            await self._redis.set(key, value, ex=ttl_s)
        except RedisError:
            self._warn()

    async def delete(self, *keys: str) -> None:
        try:
            if keys:
                await self._redis.delete(*keys)
        except RedisError:
            self._warn()

    async def version(self, namespace: str) -> int:
        """Текущая версия пространства ключей (0, если записей не было)."""
        try:
            v = await self._redis.get(f'ver:{namespace}')
            return int(v) if v else 0
        except RedisError:
            self._warn()
            return -1  # «версия неизвестна»: читатель уйдёт мимо кэша

    async def bump(self, namespace: str) -> None:
        """Инвалидация пространства: все ключи прежней версии осиротели."""
        try:
            await self._redis.incr(f'ver:{namespace}')
        except RedisError:
            self._warn()

    async def get_or_load(self, namespace: str, suffix: str, adapter: TypeAdapter,
                          loader: Callable[[], Awaitable[Any]],
                          ttl_s: int | None = None) -> Any:
        """Read-through для версионируемого пространства (паттерн справочников).

        Ключ включает версию пространства; loader выполняется на промахе,
        его результат кэшируется через adapter. version() == -1 (Redis мёртв)
        — работаем мимо кэша. Исключения loader'а (404 и т.п.) не кэшируются.
        """
        ver = await self.version(namespace)
        key = f'{namespace}:{ver}:{suffix}'
        if ver >= 0 and (hit := await self.get(key)) is not None:
            return adapter.validate_json(hit)
        value = await loader()
        if ver >= 0:
            await self.set(key, adapter.dump_json(adapter.validate_python(value)).decode(),
                           ttl_s if ttl_s is not None else settings.cache_ttl_ref_s)
        return value

    def _warn(self) -> None:
        if not self._warned:
            self._warned = True
            logger.warning('Redis недоступен (%s) — работаем без кэша', settings.redis_uri)


@lru_cache
def get_cache() -> Cache:
    return Cache(settings.redis_uri)
