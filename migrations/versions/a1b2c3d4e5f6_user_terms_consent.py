"""user: согласие на обработку ПДн (версия документа + момент)

Юридический след факта согласия при регистрации: на какую редакцию документов
пользователь согласился и когда. NULL — учётки, заведённые до ввода механизма.

Revision ID: a1b2c3d4e5f6
Revises: d2656b73fc06
Create Date: 2026-07-21

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'd2656b73fc06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# IF NOT EXISTS: baseline-ревизия делает create_all из текущей metadata, поэтому
# на ЧИСТОЙ БД (CI/новый деплой) колонки уже созданы ею; на СУЩЕСТВУЮЩЕМ проде
# baseline их не создавал — здесь добавятся. Одна миграция для обоих случаев.
def upgrade() -> None:
    op.execute('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS terms_version VARCHAR')
    op.execute('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS '
               'terms_accepted_at TIMESTAMP WITH TIME ZONE')


def downgrade() -> None:
    op.execute('ALTER TABLE "user" DROP COLUMN IF EXISTS terms_accepted_at')
    op.execute('ALTER TABLE "user" DROP COLUMN IF EXISTS terms_version')
