"""add warranty_end_date to sales_docs

Revision ID: 608568a5dcaf
Revises: PUT_YOUR_DOWN_REVISION_HERE
Create Date: 2026-02-10

"""
from alembic import op
import sqlalchemy as sa

revision = "608568a5dcaf"
down_revision = "130fbe6599d6"
branch_labels = None
depends_on = None



def upgrade():
    op.add_column("sales_docs", sa.Column("warranty_end_date", sa.Date(), nullable=True))


def downgrade():
    op.drop_column("sales_docs", "warranty_end_date")
