from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Index, func

from . import db


class TimestampMixin:
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class Project(db.Model, TimestampMixin):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), nullable=False, unique=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    customer_name = db.Column(db.String(200), nullable=True)
    location = db.Column(db.String(200), nullable=True)

    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    work_days = db.Column(db.Integer, nullable=False, default=0)

    # statuses: IN_PROGRESS, DEFECT, DONE
    status = db.Column(db.String(30), nullable=False, default="IN_PROGRESS")

    materials = db.relationship(
        "MaterialItem", backref="project", lazy=True, cascade="all, delete-orphan", order_by="MaterialItem.id"
    )
    subcontractors = db.relationship(
        "SubcontractorPayment", backref="project", lazy=True, cascade="all, delete-orphan", order_by="SubcontractorPayment.id"
    )
    expenses = db.relationship(
        "OtherExpense", backref="project", lazy=True, cascade="all, delete-orphan", order_by="OtherExpense.id"
    )

    __table_args__ = (
        Index("ix_projects_code", "code"),
        Index("ix_projects_name", "name"),
        CheckConstraint("work_days >= 0", name="ck_projects_work_days_nonneg"),
    )

    @property
    def total_material_cost(self) -> float:
        return float(sum((m.total_cost or 0) for m in self.materials))

    @property
    def total_subcontractor_cost(self) -> float:
        # จ่ายจริง = ว่าจ้าง - หัก ณ ที่จ่าย (ตามจำนวนเงินที่คีย์)
        return float(sum((s.payable_amount or 0) for s in self.subcontractors))

    @property
    def total_other_expense(self) -> float:
        return float(sum((e.amount or 0) for e in self.expenses))

    @property
    def total_cost(self) -> float:
        return float(self.total_material_cost + self.total_subcontractor_cost + self.total_other_expense)


class MaterialItem(db.Model, TimestampMixin):
    __tablename__ = "material_items"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)

    brand = db.Column(db.String(120), nullable=True)
    item_code = db.Column(db.String(80), nullable=True)  # รหัส/sku
    item_name = db.Column(db.String(200), nullable=True)
    unit = db.Column(db.String(40), nullable=True)

    unit_price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    qty = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    note = db.Column(db.String(200), nullable=True)

    __table_args__ = (
        CheckConstraint("unit_price >= 0", name="ck_material_unit_price_nonneg"),
        CheckConstraint("qty >= 0", name="ck_material_qty_nonneg"),
    )

    @property
    def total_cost(self) -> float:
        return float((self.unit_price or 0) * (self.qty or 0))


class SubcontractorPayment(db.Model, TimestampMixin):
    __tablename__ = "subcontractor_payments"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)

    vendor_name = db.Column(db.String(200), nullable=False)
    contract_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    # ภาษีหัก ณ ที่จ่าย (เปอร์เซ็นต์) เช่น 3
    withholding_rate = db.Column(db.Numeric(6, 2), nullable=False, default=0)
    withholding_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    note = db.Column(db.String(200), nullable=True)

    __table_args__ = (
        CheckConstraint("contract_amount >= 0", name="ck_sub_contract_amount_nonneg"),
        CheckConstraint("withholding_rate >= 0", name="ck_sub_wht_rate_nonneg"),
        CheckConstraint("withholding_amount >= 0", name="ck_sub_wht_amount_nonneg"),
    )

    @property
    def payable_amount(self) -> float:
        # จ่ายจริง
        return float((self.contract_amount or 0) - (self.withholding_amount or 0))


class OtherExpense(db.Model, TimestampMixin):
    __tablename__ = "other_expenses"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)

    category = db.Column(db.String(80), nullable=False, default="อื่นๆ")
    title = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    note = db.Column(db.String(200), nullable=True)

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_other_amount_nonneg"),
        Index("ix_other_expenses_category", "category"),
    )


def dashboard_aggregates() -> dict:
    """Aggregate totals for dashboard."""
    # รวมแยกหมวด
    materials_total = db.session.query(func.coalesce(func.sum(MaterialItem.unit_price * MaterialItem.qty), 0)).scalar() or 0
    subs_payable_total = db.session.query(func.coalesce(func.sum(SubcontractorPayment.contract_amount - SubcontractorPayment.withholding_amount), 0)).scalar() or 0
    other_total = db.session.query(func.coalesce(func.sum(OtherExpense.amount), 0)).scalar() or 0

    # หมวดค่าใช้จ่ายอื่นๆ แยกตาม category
    rows = (
        db.session.query(OtherExpense.category, func.coalesce(func.sum(OtherExpense.amount), 0))
        .group_by(OtherExpense.category)
        .order_by(func.sum(OtherExpense.amount).desc())
        .all()
    )
    other_by_category = [{"category": c, "total": float(t)} for c, t in rows]

    # นับสถานะโครงการ
    status_rows = (
        db.session.query(Project.status, func.count(Project.id))
        .group_by(Project.status)
        .all()
    )
    projects_by_status = {s: int(n) for s, n in status_rows}

    return {
        "materials_total": float(materials_total),
        "subcontractors_total": float(subs_payable_total),
        "other_total": float(other_total),
        "grand_total": float(materials_total + subs_payable_total + other_total),
        "other_by_category": other_by_category,
        "projects_by_status": projects_by_status,
    }
