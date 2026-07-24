"""Separate standard profile facts from situational diary measurements.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-24

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Старые стандартные показатели не имели source. Дневниковые уже помечены
    # source=diary, поэтому их не затрагиваем.
    op.execute("""
        UPDATE property AS p
        SET value = p.value || '{"source":"profile"}'::jsonb
        WHERE p."table" = 'pseudonym'
          AND p.category IN (
              SELECT vital.id
              FROM category AS vital
              JOIN category AS medical ON medical.id = vital.category
              WHERE vital.code = 'vital'
                AND medical.code = 'medical'
                AND medical.category IS NULL
          )
          AND NOT p.value ? 'source'
    """)
    # baseline на чистой БД вызывает metadata.create_all и уже видит индекс из
    # текущей модели; IF NOT EXISTS делает шаг корректным и для fresh install,
    # и для обновления ранее развёрнутой схемы.
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_property_active_profile
        ON property ("table", objectid, category, code) NULLS NOT DISTINCT
        WHERE ends IS NULL
          AND version_of IS NULL
          AND value ->> 'source' = 'profile'
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_property_active_profile")
    # source=profile уже мог быть записан приложением после миграции; удалять
    # его при downgrade нельзя без потери происхождения данных.
