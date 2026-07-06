"""RLS-слой: роль research видит только операционные данные и справочники.

Реализация плана доступа по доменам (память проекта: domain-access-plan).
DDL генерируется из metadata — списки таблиц и доменов не дублируются руками:

- якорные таблицы: identity-домен (person, user, message, access, ...) роли
  research не видны вовсе (нет GRANT); operational/reference — SELECT;
- CrossTable-таблицы (домен — свойство строки): SELECT + политика RLS,
  пропускающая только строки operational/reference доменов через реестр;
- мост (link) исключён явно: на него нет ни GRANT, ни политики;
- реестр object читается (связей он не содержит).

Аддитивно и идемпотентно: приложение подключается владельцем схемы (shop)
и обходит RLS — политики действуют только на ограниченные роли. Вызывать
apply_rls после create_all (пересоздание схемы уничтожает гранты и политики,
роль — кластерная, переживает). Ужесточение роли самого приложения
(перевод с владельца на непривилегированную роль + FORCE ROW LEVEL SECURITY)
— отдельный шаг перед продом.
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from .settings import settings
from .tables import Base, CrossTable, Domain, Link, ObjectRegistry

RESEARCH_ROLE = 'research'
POLICY_NAME = 'research_domain'

_READABLE_DOMAINS = (Domain.OPERATIONAL, Domain.REFERENCE)


def _classified() -> tuple[list[str], list[str]]:
    """(якорные таблицы, читаемые research), (CrossTable-таблицы под RLS)."""
    anchors, crosstables = [], []
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        if not issubclass(cls, Base):
            continue  # служебные Root-таблицы (реестр, пул) — отдельно
        if issubclass(cls, CrossTable):
            if cls is not Link:  # мост не читается никем, кроме приложения
                crosstables.append(cls.__tablename__)
        elif cls.__domain__ in _READABLE_DOMAINS:
            anchors.append(cls.__tablename__)
    return sorted(anchors), sorted(crosstables)


def rls_statements() -> list[str]:
    anchors, crosstables = _classified()
    domains = ', '.join(f"'{d.value}'" for d in _READABLE_DOMAINS)
    stmts = [
        # роль кластерная: создаём при отсутствии, пароль держим по настройкам
        f"""DO $$ BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{RESEARCH_ROLE}') THEN
                CREATE ROLE {RESEARCH_ROLE} LOGIN;
            END IF;
        END $$""",
        f"ALTER ROLE {RESEARCH_ROLE} LOGIN PASSWORD '{settings.research_password}'",
        f"GRANT USAGE ON SCHEMA public TO {RESEARCH_ROLE}",
        f"GRANT SELECT ON {ObjectRegistry.__tablename__} TO {RESEARCH_ROLE}",
    ]
    for table in anchors + crosstables:
        stmts.append(f'GRANT SELECT ON "{table}" TO {RESEARCH_ROLE}')
    for table in crosstables:
        stmts += [
            f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY',
            f'DROP POLICY IF EXISTS {POLICY_NAME} ON "{table}"',
            f'''CREATE POLICY {POLICY_NAME} ON "{table}"
                FOR SELECT TO {RESEARCH_ROLE}
                USING (EXISTS (SELECT 1 FROM object o
                               WHERE o.id = "{table}".id
                                 AND o.domain IN ({domains})))''',
        ]
    return stmts


async def apply_rls(conn: AsyncConnection) -> None:
    """Применяет роль/гранты/политики; вызывать после create_all."""
    for stmt in rls_statements():
        await conn.execute(text(stmt))
