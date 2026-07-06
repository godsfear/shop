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
from typing import Any

import redis.asyncio as aioredis
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

    def _warn(self) -> None:
        if not self._warned:
            self._warned = True
            logger.warning('Redis недоступен (%s) — работаем без кэша', settings.redis_uri)


@lru_cache
def get_cache() -> Cache:
    return Cache(settings.redis_uri)
