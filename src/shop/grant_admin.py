"""Назначить/снять роль админа по email — первый админ заводится этим (API
set_roles сам требует админа, иначе курица-яйцо).

  docker compose run --rm api python -m shop.grant_admin you@example.com
  docker compose run --rm api python -m shop.grant_admin you@example.com --revoke
"""
import asyncio
import sys

from sqlalchemy import select

from .database import db_helper
from .settings import settings
from .tables import User
from .versioning import versioned_update


async def _main(email: str, revoke: bool) -> None:
    async with db_helper.session_factory() as s:
        user = (await s.execute(select(User).where(
            User.contact['email'].astext == email))).scalar_one_or_none()
        if user is None:
            sys.exit(f'нет пользователя с email {email}')
        roles = [r for r in (user.roles or []) if r != settings.admin_role]
        if not revoke:
            roles.append(settings.admin_role)
        # versioned_update: история версий = аудит выдачи роли (как в set_roles)
        await versioned_update(s, User, user.id, {'roles': roles})
        await s.commit()
        print(f'{email}: roles={roles}')


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    if not args:
        sys.exit('укажите email: python -m shop.grant_admin <email> [--revoke]')
    asyncio.run(_main(args[0], '--revoke' in sys.argv))
