"""current updates

Revision ID: 766ef6e6e136
Revises: 
Create Date: 2023-09-01 21:00:11.795399

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '766ef6e6e136'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('ix_currency_iso', table_name='currency')
    op.drop_index('ix_currency_iso_num', table_name='currency')
    op.create_index(op.f('ix_currency_code'), 'currency', ['code'], unique=False)
    op.create_index(op.f('ix_currency_num'), 'currency', ['num'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_currency_num'), table_name='currency')
    op.drop_index(op.f('ix_currency_code'), table_name='currency')
    op.create_index('ix_currency_iso_num', 'currency', ['num'], unique=False)
    op.create_index('ix_currency_iso', 'currency', ['code'], unique=False)
    # ### end Alembic commands ###
