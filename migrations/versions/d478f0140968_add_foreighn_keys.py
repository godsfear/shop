"""add foreighn keys

Revision ID: d478f0140968
Revises: 0532b75f5def
Create Date: 2023-03-31 20:07:30.660979

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd478f0140968'
down_revision = '0532b75f5def'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('ix_currency_numcode', table_name='currency')
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_index('ix_currency_numcode', 'currency', ['numcode'], unique=False)
    # ### end Alembic commands ###