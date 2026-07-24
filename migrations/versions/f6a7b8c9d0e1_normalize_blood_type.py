"""Store blood type as one versioned profile fact.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-24

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_BLOOD_CATEGORY = """
    SELECT blood.id
    FROM category AS blood
    JOIN category AS medical ON medical.id = blood.category
    WHERE blood.code = 'blood'
      AND medical.code = 'medical'
      AND medical.category IS NULL
"""


def upgrade() -> None:
    # Старый UI позволял добавить несколько разных кодов группы крови.
    # Оставляем текущим самый поздний факт; остальные не удаляем, а закрываем.
    op.execute(f"""
        WITH ranked AS (
            SELECT p.id,
                   row_number() OVER (
                       PARTITION BY p."table", p.objectid, p.category
                       ORDER BY p.begins DESC, p.id DESC
                   ) AS position
            FROM property AS p
            WHERE p."table" = 'pseudonym'
              AND p.category IN ({_BLOOD_CATEGORY})
              AND p.ends IS NULL
              AND p.version_of IS NULL
        )
        UPDATE property AS p
        SET ends = now(),
            value = p.value || jsonb_build_object(
                'value', CASE
                    WHEN p.code = 'blood_type' THEN p.value -> 'value'
                    ELSE to_jsonb(p.code)
                END,
                'source', 'profile'
            )
        FROM ranked
        WHERE ranked.id = p.id
          AND ranked.position > 1
    """)

    # Стабильный code означает один логический факт. Последующие изменения
    # идут через versioned_update и остаются в истории того же id.
    op.execute(f"""
        UPDATE property AS p
        SET code = 'blood_type',
            name = 'Группа крови',
            value = p.value || jsonb_build_object(
                'value', CASE
                    WHEN p.code = 'blood_type' THEN p.value -> 'value'
                    ELSE to_jsonb(p.code)
                END,
                'source', 'profile'
            )
        WHERE p."table" = 'pseudonym'
          AND p.category IN ({_BLOOD_CATEGORY})
          AND p.ends IS NULL
          AND p.version_of IS NULL
    """)


def downgrade() -> None:
    # Возвращаем старое представление только для текущего факта. Закрытые
    # дубликаты остаются закрытыми: повторно активировать их небезопасно.
    op.execute(f"""
        UPDATE property AS p
        SET code = p.value ->> 'value',
            value = (p.value - 'value') || '{{"status":"present"}}'::jsonb
        WHERE p."table" = 'pseudonym'
          AND p.category IN ({_BLOOD_CATEGORY})
          AND p.code = 'blood_type'
          AND p.ends IS NULL
          AND p.version_of IS NULL
          AND p.value ? 'value'
    """)
