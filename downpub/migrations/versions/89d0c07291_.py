"""empty message

Revision ID: 89d0c07291
Revises: 361053ce8ba
Create Date: 2014-11-10 16:20:18.871211

"""

# revision identifiers, used by Alembic.
revision = '89d0c07291'
down_revision = '361053ce8ba'

from alembic import op
import sqlalchemy as sa


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.add_column('books', sa.Column('language', sa.String(length=5), nullable=True))
    op.add_column('books', sa.Column('rights', sa.String(length=255), nullable=True))
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('books', 'rights')
    op.drop_column('books', 'language')
    ### end Alembic commands ###
