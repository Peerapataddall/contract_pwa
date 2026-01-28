"""add timestamps to sales docs

Revision ID: REV_ID_HERE
Revises: 3ea974bb2cc7
Create Date: 2026-01-26
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "af34e755eb65"
down_revision = "3ea974bb2cc7"
branch_labels = None
depends_on = None


def upgrade():
    # sales_docs timestamps
    op.execute("""ALTER TABLE sales_docs ADD COLUMN IF NOT EXISTS created_at TIMESTAMP;""")
    op.execute("""ALTER TABLE sales_docs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;""")

    # sales_items timestamps
    op.execute("""ALTER TABLE sales_items ADD COLUMN IF NOT EXISTS created_at TIMESTAMP;""")
    op.execute("""ALTER TABLE sales_items ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;""")


def downgrade():
    pass
