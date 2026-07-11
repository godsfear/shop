"""Контент-адресованное файлохранилище.

Единственный шов — put(bytes)->{hash,algorithm,size} / get(hash)->bytes; за ним
сейчас Postgres (таблица Blob), позже S3/MinIO без изменения вызывающих. Дедуп
даёт контент-адресация: hash = PK блоба, повторная запись тех же байт — no-op.
Метаданные (что это за файл, чей) хранит Data на псевдониме/эпизоде — они несут
чувствительность и домен; сам блоб обезличен.
"""
import hashlib

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..database import db_helper
from .. import tables

ALGORITHM = 'sha256'


class FileStore:
    def __init__(self, session=Depends(db_helper.scoped_session_dependency)):
        self.session = session

    async def put(self, content: bytes) -> dict:
        """Кладёт байты, возвращает {hash, algorithm, size}. Идемпотентно (дедуп по hash)."""
        digest = hashlib.sha256(content).hexdigest()
        await self.session.execute(
            pg_insert(tables.Blob)
            .values(hash=digest, algorithm=ALGORITHM, size=len(content), content=content)
            .on_conflict_do_nothing(index_elements=['hash']))
        await self.session.commit()
        return {'hash': digest, 'algorithm': ALGORITHM, 'size': len(content)}

    async def get(self, digest: str) -> bytes | None:
        return (await self.session.execute(
            select(tables.Blob.content).where(tables.Blob.hash == digest))).scalar_one_or_none()

    async def exists(self, digest: str) -> bool:
        return (await self.session.execute(
            select(tables.Blob.hash).where(tables.Blob.hash == digest))).scalar_one_or_none() is not None
