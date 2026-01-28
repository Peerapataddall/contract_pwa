"""add project link and boq fields

Revision ID: 031fc2819639
Revises: f387e2a8c9b2
Create Date: 2026-01-29 00:21:01.889912

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '031fc2819639'
down_revision = 'f387e2a8c9b2'
branch_labels = None
depends_on = None


def upgrade():
    import sqlalchemy as sa
    from alembic import op

    with op.batch_alter_table('projects') as batch_op:
        batch_op.add_column(sa.Column('sales_doc_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('boq_excel_path', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('boq_pdf_path', sa.String(length=255), nullable=True))

        batch_op.create_unique_constraint(
            'uq_projects_sales_doc_id', ['sales_doc_id']
        )
        batch_op.create_foreign_key(
            'fk_projects_sales_doc_id',
            'sales_docs',
            ['sales_doc_id'],
            ['id'],
            ondelete='SET NULL'
        )


def downgrade():
    import sqlalchemy as sa
    from alembic import op

    with op.batch_alter_table('projects') as batch_op:
        batch_op.drop_constraint('fk_projects_sales_doc_id', type_='foreignkey')
        batch_op.drop_constraint('uq_projects_sales_doc_id', type_='unique')
        batch_op.drop_column('boq_pdf_path')
        batch_op.drop_column('boq_excel_path')
        batch_op.drop_column('sales_doc_id')

