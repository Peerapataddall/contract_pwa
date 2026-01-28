"""add sales docs

Revision ID: REV_ID_HERE
Revises: 21e2b83223a3
Create Date: 2026-01-26
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "3ea974bb2cc7"
down_revision = "21e2b83223a3"
branch_labels = None
depends_on = None


def upgrade():
    # สร้างตาราง sales_docs
    op.execute("""
    CREATE TABLE IF NOT EXISTS sales_docs (
        id SERIAL PRIMARY KEY,
        doc_type VARCHAR(10) NOT NULL DEFAULT 'QT',
        doc_no VARCHAR(40) NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',

        issue_date DATE NOT NULL DEFAULT CURRENT_DATE,
        due_date DATE NULL,

        company_name VARCHAR(200),
        company_tax_id VARCHAR(40),
        company_address TEXT,
        company_phone VARCHAR(80),
        company_email VARCHAR(120),
        company_website VARCHAR(120),
        company_logo_path VARCHAR(255),

        customer_name VARCHAR(200) NOT NULL,
        customer_tax_id VARCHAR(40),
        customer_address TEXT,
        customer_phone VARCHAR(80),
        customer_email VARCHAR(120),

        subject VARCHAR(255),
        description TEXT,

        discount_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
        vat_rate NUMERIC(5,2) NOT NULL DEFAULT 7,
        wht_rate NUMERIC(5,2) NOT NULL DEFAULT 0,

        note TEXT,
        deposit_note TEXT,
        warranty_months INTEGER,
        payment_terms TEXT,

        approved_by VARCHAR(120),
        approved_at TIMESTAMP NULL,

        parent_id INTEGER NULL
    );
    """)

    # unique + index
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS ux_sales_docs_doc_no ON sales_docs(doc_no);""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_sales_docs_doc_type ON sales_docs(doc_type);""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_sales_docs_status ON sales_docs(status);""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_sales_docs_parent_id ON sales_docs(parent_id);""")

    # FK parent_id -> sales_docs.id
    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_sales_docs_parent'
      ) THEN
        ALTER TABLE sales_docs
          ADD CONSTRAINT fk_sales_docs_parent
          FOREIGN KEY (parent_id) REFERENCES sales_docs(id)
          ON DELETE SET NULL;
      END IF;
    END $$;
    """)

    # สร้างตาราง sales_items
    op.execute("""
    CREATE TABLE IF NOT EXISTS sales_items (
        id SERIAL PRIMARY KEY,
        doc_id INTEGER NOT NULL,
        description TEXT NOT NULL,
        qty NUMERIC(12,2) NOT NULL DEFAULT 1,
        unit_price NUMERIC(12,2) NOT NULL DEFAULT 0,
        discount_amount NUMERIC(12,2) NOT NULL DEFAULT 0
    );
    """)

    op.execute("""CREATE INDEX IF NOT EXISTS ix_sales_items_doc_id ON sales_items(doc_id);""")

    # FK sales_items.doc_id -> sales_docs.id
    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_sales_items_doc'
      ) THEN
        ALTER TABLE sales_items
          ADD CONSTRAINT fk_sales_items_doc
          FOREIGN KEY (doc_id) REFERENCES sales_docs(id)
          ON DELETE CASCADE;
      END IF;
    END $$;
    """)


def downgrade():
    # ไม่ drop เพื่อความปลอดภัย
    pass
