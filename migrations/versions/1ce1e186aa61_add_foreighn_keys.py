"""add foreighn keys

Revision ID: 1ce1e186aa61
Revises: 24e30abec06f
Create Date: 2023-03-31 14:41:15.961941

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1ce1e186aa61'
down_revision = '24e30abec06f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('currency', sa.Column('numcode', sa.String(), nullable=True))
    op.create_index(op.f('ix_currency_numcode'), 'currency', ['numcode'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_currency_numcode'), table_name='currency')
    op.drop_column('currency', 'numcode')
    # ### end Alembic commands ###
