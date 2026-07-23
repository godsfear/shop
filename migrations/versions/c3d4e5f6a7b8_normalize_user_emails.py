"""Normalize stored user emails

Existing JSONB contacts may predate the lowercase application rule.  Canonicalize
them once so stored values, lookups, and Redis keys use the same form.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-24

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE "user"
        SET contact = jsonb_set(
            contact,
            '{email}',
            to_jsonb(lower(btrim(contact ->> 'email'))),
            true
        )
        WHERE contact ? 'email'
          AND contact ->> 'email' IS NOT NULL
          AND contact ->> 'email' IS DISTINCT FROM lower(btrim(contact ->> 'email'))
    """)


def downgrade() -> None:
    # Нормализация необратима: исходный регистр и пробелы восстановить нельзя.
    pass
