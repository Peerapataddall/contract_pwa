"""add boq attachments to sales_docs

Revision ID: f387e2a8c9b2
Revises: af34e755eb65
Create Date: 2026-01-28 16:38:49.362339
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f387e2a8c9b2"
down_revision = "af34e755eb65"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("sales_docs", sa.Column("boq_excel_path", sa.String(length=255), nullable=True))
    op.add_column("sales_docs", sa.Column("boq_pdf_path", sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column("sales_docs", "boq_pdf_path")
    op.drop_column("sales_docs", "boq_excel_path")
