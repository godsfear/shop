"""person: место жительства (residence: {country, city})

Свободный текст страны/города проживания; уходит в ИИ-оценки как контекст.
NULL — персоны, заведённые до ввода поля.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-22

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# IF NOT EXISTS: на чистой БД (CI/новый деплой) колонку уже создал baseline
# create_all из текущей metadata; на существующем проде — добавится здесь.
def upgrade() -> None:
    op.execute('ALTER TABLE person ADD COLUMN IF NOT EXISTS residence JSONB')


def downgrade() -> None:
    op.execute('ALTER TABLE person DROP COLUMN IF EXISTS residence')
