"""baseline schema

Бутстрап всей текущей схемы из metadata (расширение postgis + все таблицы,
индексы, составные FK, частичные уникальные индексы). Дальнейшие изменения
схемы — обычными autogenerate-ревизиями поверх этой базы.

RLS-роль research и политики применяются ОТДЕЛЬНО после миграций:
    from shop.security import apply_rls  (см. docstring security.py)

Revision ID: d2656b73fc06
Revises:
Create Date: 2026-07-06 22:32:29

"""
from typing import Sequence, Union

from alembic import op

from shop.tables import Root

# revision identifiers, used by Alembic.
revision: str = 'd2656b73fc06'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS postgis')
    Root.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Root.metadata.drop_all(bind=op.get_bind())
