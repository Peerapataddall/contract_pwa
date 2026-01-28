"""add customers and link to sales_docs

Revision ID: b1c0d1e2f3a4
Revises: f387e2a8c9b2
Create Date: 2026-01-28 17:48:29

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b1c0d1e2f3a4"
down_revision = "f387e2a8c9b2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("tax_id", sa.String(length=40), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("phone", sa.String(length=80), nullable=True),
        sa.Column("email", sa.String(length=120), nullable=True),
        sa.Column("contact_name", sa.String(length=120), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_customers_name", "customers", ["name"])

    with op.batch_alter_table("sales_docs") as batch_op:
        batch_op.add_column(sa.Column("customer_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_sales_docs_customer_id", ["customer_id"])
        batch_op.create_foreign_key(
            "fk_sales_docs_customer_id",
            "customers",
            ["customer_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade():
    with op.batch_alter_table("sales_docs") as batch_op:
        batch_op.drop_constraint("fk_sales_docs_customer_id", type_="foreignkey")
        batch_op.drop_index("ix_sales_docs_customer_id")
        batch_op.drop_column("customer_id")

    op.drop_index("ix_customers_name", table_name="customers")
    op.drop_table("customers")
