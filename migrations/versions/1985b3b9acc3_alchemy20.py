"""alchemy20

Revision ID: 1985b3b9acc3
Revises: fd2f6e59a536
Create Date: 2024-02-04 19:37:13.501193

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1985b3b9acc3'
down_revision = 'fd2f6e59a536'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_unique_constraint(None, 'access', ['id'])
    op.create_unique_constraint(None, 'account', ['id'])
    op.create_unique_constraint(None, 'address', ['id'])
    op.create_unique_constraint(None, 'category', ['id'])
    op.create_unique_constraint(None, 'company', ['id'])
    op.create_unique_constraint(None, 'country', ['id'])
    op.create_unique_constraint(None, 'currency', ['id'])
    op.create_unique_constraint(None, 'data', ['id'])
    op.create_unique_constraint(None, 'document', ['id'])
    op.create_unique_constraint(None, 'entity', ['id'])
    op.create_unique_constraint(None, 'language', ['id'])
    op.create_unique_constraint(None, 'message', ['id'])
    op.create_unique_constraint(None, 'operation', ['id'])
    op.create_unique_constraint(None, 'person', ['id'])
    op.create_unique_constraint(None, 'picture', ['id'])
    op.create_unique_constraint(None, 'place', ['id'])
    op.create_unique_constraint(None, 'position', ['id'])
    op.create_unique_constraint(None, 'procedure', ['id'])
    op.create_unique_constraint(None, 'property', ['id'])
    op.create_unique_constraint(None, 'rate', ['id'])
    op.create_unique_constraint(None, 'relation', ['id'])
    op.create_unique_constraint(None, 'state', ['id'])
    op.create_unique_constraint(None, 'translation', ['id'])
    op.create_unique_constraint(None, 'user', ['id'])
    op.create_foreign_key(None, 'user', 'person', ['person'], ['id'])
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, 'user', type_='foreignkey')
    op.drop_constraint(None, 'user', type_='unique')
    op.drop_constraint(None, 'translation', type_='unique')
    op.drop_constraint(None, 'state', type_='unique')
    op.drop_constraint(None, 'relation', type_='unique')
    op.drop_constraint(None, 'rate', type_='unique')
    op.drop_constraint(None, 'property', type_='unique')
    op.drop_constraint(None, 'procedure', type_='unique')
    op.drop_constraint(None, 'position', type_='unique')
    op.drop_constraint(None, 'place', type_='unique')
    op.drop_constraint(None, 'picture', type_='unique')
    op.drop_constraint(None, 'person', type_='unique')
    op.drop_constraint(None, 'operation', type_='unique')
    op.drop_constraint(None, 'message', type_='unique')
    op.drop_constraint(None, 'language', type_='unique')
    op.drop_constraint(None, 'entity', type_='unique')
    op.drop_constraint(None, 'document', type_='unique')
    op.drop_constraint(None, 'data', type_='unique')
    op.drop_constraint(None, 'currency', type_='unique')
    op.drop_constraint(None, 'country', type_='unique')
    op.drop_constraint(None, 'company', type_='unique')
    op.drop_constraint(None, 'category', type_='unique')
    op.drop_constraint(None, 'address', type_='unique')
    op.drop_constraint(None, 'account', type_='unique')
    op.drop_constraint(None, 'access', type_='unique')
    # ### end Alembic commands ###