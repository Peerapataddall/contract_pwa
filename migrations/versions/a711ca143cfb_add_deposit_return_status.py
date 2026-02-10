"""add deposit return status

Revision ID: a711ca143cfb
Revises: 9deab562fa97
Create Date: 2026-02-10
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a711ca143cfb"
down_revision = "9deab562fa97"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "projects",
        sa.Column("deposit_returned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "projects",
        sa.Column("deposit_returned_at", sa.Date(), nullable=True),
    )
    op.alter_column("projects", "deposit_returned", server_default=None)


def downgrade():
    op.drop_column("projects", "deposit_returned_at")
    op.drop_column("projects", "deposit_returned")
