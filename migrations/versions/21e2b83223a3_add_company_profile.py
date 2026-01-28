"""add company profile

Revision ID: 21e2b83223a3
Revises: 72e596dd2ce1
Create Date: 2026-01-26
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "21e2b83223a3"
down_revision = "72e596dd2ce1"
branch_labels = None
depends_on = None


def upgrade():
    # Postgres: สร้างตารางถ้ายังไม่มี
    op.execute("""
    CREATE TABLE IF NOT EXISTS company_profiles (
        id SERIAL PRIMARY KEY
    );
    """)

    # เพิ่มคอลัมน์ถ้ายังไม่มี (กันชนกับ DB เดิม)
    op.execute("""ALTER TABLE company_profiles ADD COLUMN IF NOT EXISTS company_name VARCHAR(200);""")
    op.execute("""ALTER TABLE company_profiles ADD COLUMN IF NOT EXISTS tax_id VARCHAR(40);""")
    op.execute("""ALTER TABLE company_profiles ADD COLUMN IF NOT EXISTS address TEXT;""")
    op.execute("""ALTER TABLE company_profiles ADD COLUMN IF NOT EXISTS phone VARCHAR(80);""")
    op.execute("""ALTER TABLE company_profiles ADD COLUMN IF NOT EXISTS email VARCHAR(120);""")
    op.execute("""ALTER TABLE company_profiles ADD COLUMN IF NOT EXISTS website VARCHAR(120);""")
    op.execute("""ALTER TABLE company_profiles ADD COLUMN IF NOT EXISTS logo_path VARCHAR(255);""")

    # เผื่อมี TimestampMixin
    op.execute("""ALTER TABLE company_profiles ADD COLUMN IF NOT EXISTS created_at TIMESTAMP;""")
    op.execute("""ALTER TABLE company_profiles ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;""")


def downgrade():
    # ไม่ drop เพื่อความปลอดภัย (กันข้อมูลหาย)
    pass
