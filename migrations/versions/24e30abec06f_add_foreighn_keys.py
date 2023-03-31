"""add foreighn keys

Revision ID: 24e30abec06f
Revises: 22a96622de99
Create Date: 2023-03-31 14:18:24.448302

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '24e30abec06f'
down_revision = '22a96622de99'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_unique_constraint(None, 'countryFlag', ['id'])
    op.add_column('currency', sa.Column('symbol_native', sa.String(), nullable=True))
    op.create_unique_constraint(None, 'language', ['id'])
    op.create_unique_constraint(None, 'translation', ['id'])
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, 'translation', type_='unique')
    op.drop_constraint(None, 'language', type_='unique')
    op.drop_column('currency', 'symbol_native')
    op.drop_constraint(None, 'countryFlag', type_='unique')
    # ### end Alembic commands ###