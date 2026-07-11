"""Роли БД и RLS: три роли под три задачи (память проекта: domain-access-plan, B.6).

- ВЛАДЕЛЕЦ (shop) — только DDL: миграции, create_all, apply_rls. На проде этот
  DSN живёт лишь на деплой-раннере.
- app — runtime-DSN приложения: SELECT/INSERT/UPDATE/DELETE и ничего больше
  (без ALTER/DROP/ролей) — компрометация приложения не даёт снести схему,
  отключить политики или завести роль. app видит все строки всех доменов
  (явная политика app_all) — это доверенный посредник, consent/manage-проверки
  живут в Python (ConsentService, bridge._ensure_manager).
- research — статистика: identity-якоря и мост не видны вовсе (нет GRANT),
  CrossTable-строки фильтруются политикой по домену из реестра object.

DDL генерируется из metadata — списки таблиц и доменов не дублируются руками.
FORCE ROW LEVEL SECURITY: политики действуют и на владельца, доступ каждой
роли — явное правило (owner_all для сида/миграций данных), а не побочный
эффект владения. Аддитивно и идемпотентно: вызывать apply_rls после
create_all (пересоздание схемы уничтожает гранты и политики; роли кластерные,
переживают). ALTER DEFAULT PRIVILEGES покрывает будущие таблицы миграций —
иначе каждая новая таблица означала бы забытый GRANT и 42501 в проде.
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from .settings import settings
from .tables import Base, CrossTable, Domain, Link, ObjectRegistry

RESEARCH_ROLE = 'research'
APP_ROLE = 'app'
POLICY_NAME = 'research_domain'

_READABLE_DOMAINS = (Domain.OPERATIONAL, Domain.REFERENCE)
_APP_GRANTS = 'SELECT, INSERT, UPDATE, DELETE'


def _pw(password: str) -> str:
    """Экранирование пароля в DDL (ALTER ROLE не параметризуется)."""
    return password.replace("'", "''")


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
        # роли кластерные: создаём при отсутствии, пароли держим по настройкам
        f"""DO $$ BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{RESEARCH_ROLE}') THEN
                CREATE ROLE {RESEARCH_ROLE} LOGIN;
            END IF;
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                CREATE ROLE {APP_ROLE} LOGIN;
            END IF;
        END $$""",
        f"ALTER ROLE {RESEARCH_ROLE} LOGIN PASSWORD '{_pw(settings.research_password)}'",
        f"ALTER ROLE {APP_ROLE} LOGIN PASSWORD '{_pw(settings.app_db_password)}'",
        # app: полный DML на всё, никакого DDL; будущие таблицы — default privileges
        f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}",
        f"GRANT {_APP_GRANTS} ON ALL TABLES IN SCHEMA public TO {APP_ROLE}",
        f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT {_APP_GRANTS} ON TABLES TO {APP_ROLE}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}",
        # research: читает реестр (связей он не содержит)
        f"GRANT USAGE ON SCHEMA public TO {RESEARCH_ROLE}",
        f"GRANT SELECT ON {ObjectRegistry.__tablename__} TO {RESEARCH_ROLE}",
    ]
    for table in anchors + crosstables:
        stmts.append(f'GRANT SELECT ON "{table}" TO {RESEARCH_ROLE}')
    for table in crosstables:
        stmts += [
            f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY',
            # FORCE: политики действуют и на владельца — доступ всякой роли явен
            f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY',
            f'DROP POLICY IF EXISTS {POLICY_NAME} ON "{table}"',
            f'''CREATE POLICY {POLICY_NAME} ON "{table}"
                FOR SELECT TO {RESEARCH_ROLE}
                USING (EXISTS (SELECT 1 FROM object o
                               WHERE o.id = "{table}".id
                                 AND o.domain IN ({domains})))''',
            f'DROP POLICY IF EXISTS app_all ON "{table}"',
            f'''CREATE POLICY app_all ON "{table}"
                FOR ALL TO {APP_ROLE} USING (true) WITH CHECK (true)''',
            # владелец: сид/миграции данных (CURRENT_USER = владелец на apply_rls)
            f'DROP POLICY IF EXISTS owner_all ON "{table}"',
            f'''CREATE POLICY owner_all ON "{table}"
                FOR ALL TO CURRENT_USER USING (true) WITH CHECK (true)''',
        ]
    return stmts


async def apply_rls(conn: AsyncConnection) -> None:
    """Применяет роль/гранты/политики; вызывать после create_all."""
    for stmt in rls_statements():
        await conn.execute(text(stmt))
