"""merge heads 031fc2819639 and b1c0d1e2f3a4

Revision ID: 130fbe6599d6
Revises: 031fc2819639, b1c0d1e2f3a4
Create Date: 2026-01-29 00:57:40.521480

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '130fbe6599d6'
down_revision = ('031fc2819639', 'b1c0d1e2f3a4')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
