"""empty message

Revision ID: 361053ce8ba
Revises: 10bac0f404c
Create Date: 2014-11-03 11:26:02.649810

"""

# revision identifiers, used by Alembic.
revision = '361053ce8ba'
down_revision = '10bac0f404c'

from alembic import op
import sqlalchemy as sa


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.add_column('books', sa.Column('displayed_name', sa.String(length=255), nullable=True))
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('books', 'displayed_name')
    ### end Alembic commands ###
