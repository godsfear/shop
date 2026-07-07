"""baseline schema

Бутстрап всей схемы из metadata через create_all. Он же (через слушатели
before_create/after_create в tables.py) создаёт расширения postgis+pg_trgm
и триггеры реестра/доменов — их autogenerate НЕ видит.

Проверено: autogenerate против БД после этой ревизии показывает «изменений
нет» (baseline полон). Дальнейшие изменения — autogenerate-ревизиями поверх.
ВАЖНО для инкрементальных ревизий: create_all там не вызывается, поэтому
новую CrossTable-таблицу автоген создаст БЕЗ её регистрационного триггера —
триггер надо добавить вручную (см. tables.trigger_statements), иначе сырые
INSERT'ы в неё не попадут в реестр объектов.

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
    # расширения и триггеры создаются слушателями metadata внутри create_all
    Root.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Root.metadata.drop_all(bind=op.get_bind())
