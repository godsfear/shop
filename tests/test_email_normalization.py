from sqlalchemy.dialects import postgresql

from shop.models.user import (Contact, PasswordReset, PasswordResetConfirm,
                              SignUpConfirm)
from shop.services.user import UserService


def test_email_is_normalized_in_every_auth_payload() -> None:
    address = '  User.Name+tag@Example.COM  '

    assert Contact(email=address).email == 'user.name+tag@example.com'
    assert SignUpConfirm(email=address, code='123456').email == 'user.name+tag@example.com'
    assert PasswordReset(email=address).email == 'user.name+tag@example.com'
    assert (PasswordResetConfirm(email=address, code='123456', password='ValidPass1')
            .email == 'user.name+tag@example.com')


class _Scalars:
    def __init__(self, user: object):
        self._user = user

    def first(self) -> object:
        return self._user


class _Result:
    def __init__(self, user: object):
        self._user = user

    def scalars(self) -> _Scalars:
        return _Scalars(self._user)


class _Session:
    def __init__(self, user: object):
        self.user = user
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _Result(self.user)


async def test_lookup_normalizes_email_before_password_check() -> None:
    expected_user = object()
    session = _Session(expected_user)

    found = await UserService(session=session).get_by_contact('  USER@Example.COM  ')

    assert found is expected_user
    compiled = session.statement.compile(dialect=postgresql.dialect())
    assert 'lower(' in str(compiled)
    assert 'user@example.com' in compiled.params.values()
