"""Move legacy episode diary entries to the shared patient record.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-24

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Раньше дневниковые замеры и заметки висели на Entity эпизода. Переносим
    # и активные, и исторические версии к его владельцу-псевдониму, сохраняя
    # идентификатор, дату и темпоральную историю записи.
    op.execute("""
        UPDATE property AS p
        SET "table" = 'pseudonym', objectid = e.objectid
        FROM entity AS e
        WHERE p."table" = 'entity'
          AND p.objectid = e.id
          AND p.value ->> 'source' = 'diary'
    """)


def downgrade() -> None:
    # Обратная связь с исходным эпизодом после переноса намеренно не хранится.
    pass
