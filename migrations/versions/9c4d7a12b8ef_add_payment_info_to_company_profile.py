"""add payment info to company profile

Revision ID: 9c4d7a12b8ef
Revises: 130fbe6599d6
Create Date: 2026-01-29

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "9c4d7a12b8ef"
down_revision = "130fbe6599d6"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("company_profiles") as batch_op:
        batch_op.add_column(sa.Column("payment_bank", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("payment_account_no", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("payment_account_name", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("payment_branch", sa.String(length=200), nullable=True))


def downgrade():
    with op.batch_alter_table("company_profiles") as batch_op:
        batch_op.drop_column("payment_branch")
        batch_op.drop_column("payment_account_name")
        batch_op.drop_column("payment_account_no")
        batch_op.drop_column("payment_bank")
