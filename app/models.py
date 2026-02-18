from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import CheckConstraint, Index, func

from . import db


class TimestampMixin:
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


# =========================================================
# Customers
# =========================================================
class Customer(db.Model, TimestampMixin):
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(200), nullable=False, index=True)
    tax_id = db.Column(db.String(40), nullable=True)
    address = db.Column(db.Text, nullable=True)
    phone = db.Column(db.String(80), nullable=True)
    email = db.Column(db.String(120), nullable=True)

    contact_name = db.Column(db.String(120), nullable=True)
    note = db.Column(db.Text, nullable=True)

    is_active = db.Column(db.Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<Customer {self.id} {self.name!r}>"


# =========================================================
# Projects
# =========================================================
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

    # -------------------------------------------------
    # ✅ Deposit return tracking (คืนเงินประกัน)
    # -------------------------------------------------
    deposit_returned = db.Column(db.Boolean, nullable=False, default=False)
    deposit_returned_at = db.Column(db.Date, nullable=True)

    # -------------------------------------------------
    # ✅ link Project <-> QT (SalesDoc) one-to-one
    # -------------------------------------------------
    sales_doc_id = db.Column(
        db.Integer,
        db.ForeignKey("sales_docs.id"),
        nullable=True,
        unique=True,
        index=True,
    )

    # ✅ BOQ paths on Project
    boq_excel_path = db.Column(db.String(255), nullable=True)
    boq_pdf_path = db.Column(db.String(255), nullable=True)

    # -------------------------------------------------
    # ✅ NOTE: ย้าย “อ้างอิงใบกำกับภาษีค่าวัสดุ” ไปอยู่ใน MaterialItem แล้ว
    # - เดิมอยู่ที่:
    #   materials_tax_invoice_no / materials_tax_invoice_date
    # -------------------------------------------------

    # relationships
    sales_doc = db.relationship(
        "SalesDoc",
        backref=db.backref("project", uselist=False),
        foreign_keys=[sales_doc_id],
        uselist=False,
    )

    materials = db.relationship(
        "MaterialItem",
        backref="project",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="MaterialItem.id",
    )
    subcontractors = db.relationship(
        "SubcontractorPayment",
        backref="project",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="SubcontractorPayment.id",
    )
    expenses = db.relationship(
        "OtherExpense",
        backref="project",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="OtherExpense.id",
    )

    # ✅ เงินเบิกล่วงหน้า
    advances = db.relationship(
        "AdvanceExpense",
        backref="project",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="AdvanceExpense.id",
    )

    __table_args__ = (
        Index("ix_projects_code", "code"),
        Index("ix_projects_name", "name"),
        Index("ix_projects_sales_doc_id", "sales_doc_id"),
        CheckConstraint("work_days >= 0", name="ck_projects_work_days_nonneg"),
    )

    @property
    def total_material_cost(self) -> float:
        return float(sum((m.total_cost or 0) for m in self.materials))

    @property
    def total_subcontractor_cost(self) -> float:
        # จ่ายจริง = ว่าจ้าง - หัก ณ ที่จ่าย
        return float(sum((s.payable_amount or 0) for s in self.subcontractors))

    @property
    def total_other_expense(self) -> float:
        return float(sum((e.amount or 0) for e in self.expenses))

    @property
    def total_advance_expense(self) -> float:
        return float(sum((a.amount or 0) for a in self.advances))

    @property
    def total_cost(self) -> float:
        return float(
            self.total_material_cost
            + self.total_subcontractor_cost
            + self.total_other_expense
            + self.total_advance_expense
        )


# =========================================================
# Material items
# =========================================================
class MaterialItem(db.Model, TimestampMixin):
    __tablename__ = "material_items"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)

    brand = db.Column(db.String(120), nullable=True)
    item_code = db.Column(db.String(80), nullable=True)  # รหัส/sku
    item_name = db.Column(db.String(200), nullable=True)
    unit = db.Column(db.String(40), nullable=True)

    # ✅ NEW: อ้างอิงใบกำกับภาษี “ต่อรายการย่อย”
    tax_invoice_no = db.Column(db.String(60), nullable=True)
    tax_invoice_date = db.Column(db.Date, nullable=True)

    unit_price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    qty = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    note = db.Column(db.String(200), nullable=True)

    __table_args__ = (
        CheckConstraint("unit_price >= 0", name="ck_material_unit_price_nonneg"),
        CheckConstraint("qty >= 0", name="ck_material_qty_nonneg"),
        Index("ix_material_items_project_id", "project_id"),
        Index("ix_material_items_tax_invoice_no", "tax_invoice_no"),
        Index("ix_material_items_tax_invoice_date", "tax_invoice_date"),
    )

    @property
    def total_cost(self) -> float:
        return float((self.unit_price or 0) * (self.qty or 0))


# =========================================================
# Subcontractor payments
# =========================================================
class SubcontractorPayment(db.Model, TimestampMixin):
    __tablename__ = "subcontractor_payments"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)

    vendor_name = db.Column(db.String(200), nullable=False)

    # ✅ วันที่จ่าย
    pay_date = db.Column(db.Date, nullable=True)

    contract_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    # ภาษีหัก ณ ที่จ่าย (%)
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


# =========================================================
# Other expenses
# =========================================================
class OtherExpense(db.Model, TimestampMixin):
    __tablename__ = "other_expenses"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)

    category = db.Column(db.String(80), nullable=False, default="อื่นๆ")

    # ✅ วันที่ค่าใช้จ่าย
    expense_date = db.Column(db.Date, nullable=True)

    title = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    note = db.Column(db.String(200), nullable=True)

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_other_amount_nonneg"),
        Index("ix_other_expenses_category", "category"),
    )


# =========================================================
# Advance expense
# =========================================================
class AdvanceExpense(db.Model, TimestampMixin):
    """
    ✅ เงินเบิกล่วงหน้า (โครงเหมือนค่าใช้จ่ายอื่น)
    - หนึ่งโครงการมีหลายรายการ
    """
    __tablename__ = "advance_expenses"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True
    )

    title = db.Column(db.String(200), nullable=False)
    advance_date = db.Column(db.Date, nullable=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    note = db.Column(db.String(200), nullable=True)

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_advance_amount_nonneg"),
        Index("ix_advance_expenses_project_id", "project_id"),
    )


# =========================================================
# Dashboard aggregates
# =========================================================
def dashboard_aggregates(year: int | None = None, month: int | None = None) -> dict:
    """
    Aggregate totals for dashboard (filtered by Project.start_date month/year if provided).
    """
    proj_q = db.session.query(Project.id)

    if year:
        proj_q = proj_q.filter(func.extract("year", Project.start_date) == int(year))
    if month:
        proj_q = proj_q.filter(func.extract("month", Project.start_date) == int(month))

    project_ids_subq = proj_q.subquery()

    materials_total = (
        db.session.query(func.coalesce(func.sum(MaterialItem.unit_price * MaterialItem.qty), 0))
        .filter(MaterialItem.project_id.in_(project_ids_subq))
        .scalar()
        or 0
    )

    subs_payable_total = (
        db.session.query(
            func.coalesce(
                func.sum(SubcontractorPayment.contract_amount - SubcontractorPayment.withholding_amount),
                0,
            )
        )
        .filter(SubcontractorPayment.project_id.in_(project_ids_subq))
        .scalar()
        or 0
    )

    other_total = (
        db.session.query(func.coalesce(func.sum(OtherExpense.amount), 0))
        .filter(OtherExpense.project_id.in_(project_ids_subq))
        .scalar()
        or 0
    )

    advances_total = (
        db.session.query(func.coalesce(func.sum(AdvanceExpense.amount), 0))
        .filter(AdvanceExpense.project_id.in_(project_ids_subq))
        .scalar()
        or 0
    )

    rows = (
        db.session.query(OtherExpense.category, func.coalesce(func.sum(OtherExpense.amount), 0))
        .filter(OtherExpense.project_id.in_(project_ids_subq))
        .group_by(OtherExpense.category)
        .order_by(func.sum(OtherExpense.amount).desc())
        .all()
    )
    other_by_category = [{"category": c, "total": float(t)} for c, t in rows]

    status_rows = (
        db.session.query(Project.status, func.count(Project.id))
        .filter(Project.id.in_(project_ids_subq))
        .group_by(Project.status)
        .all()
    )
    projects_by_status = {s: int(n) for s, n in status_rows}

    mat_rows = (
        db.session.query(
            MaterialItem.project_id.label("pid"),
            func.coalesce(func.sum(MaterialItem.unit_price * MaterialItem.qty), 0).label("materials"),
        )
        .filter(MaterialItem.project_id.in_(project_ids_subq))
        .group_by(MaterialItem.project_id)
        .subquery()
    )

    sub_rows = (
        db.session.query(
            SubcontractorPayment.project_id.label("pid"),
            func.coalesce(
                func.sum(SubcontractorPayment.contract_amount - SubcontractorPayment.withholding_amount),
                0,
            ).label("subs"),
        )
        .filter(SubcontractorPayment.project_id.in_(project_ids_subq))
        .group_by(SubcontractorPayment.project_id)
        .subquery()
    )

    oth_rows = (
        db.session.query(
            OtherExpense.project_id.label("pid"),
            func.coalesce(func.sum(OtherExpense.amount), 0).label("expenses"),
        )
        .filter(OtherExpense.project_id.in_(project_ids_subq))
        .group_by(OtherExpense.project_id)
        .subquery()
    )

    adv_rows = (
        db.session.query(
            AdvanceExpense.project_id.label("pid"),
            func.coalesce(func.sum(AdvanceExpense.amount), 0).label("advances"),
        )
        .filter(AdvanceExpense.project_id.in_(project_ids_subq))
        .group_by(AdvanceExpense.project_id)
        .subquery()
    )

    top5_q = (
        db.session.query(
            Project.code.label("code"),
            Project.name.label("name"),
            func.coalesce(mat_rows.c.materials, 0).label("materials"),
            func.coalesce(sub_rows.c.subs, 0).label("subs"),
            func.coalesce(oth_rows.c.expenses, 0).label("expenses"),
            func.coalesce(adv_rows.c.advances, 0).label("advances"),
            (
                func.coalesce(mat_rows.c.materials, 0)
                + func.coalesce(sub_rows.c.subs, 0)
                + func.coalesce(oth_rows.c.expenses, 0)
                + func.coalesce(adv_rows.c.advances, 0)
            ).label("total"),
        )
        .filter(Project.id.in_(project_ids_subq))
        .outerjoin(mat_rows, mat_rows.c.pid == Project.id)
        .outerjoin(sub_rows, sub_rows.c.pid == Project.id)
        .outerjoin(oth_rows, oth_rows.c.pid == Project.id)
        .outerjoin(adv_rows, adv_rows.c.pid == Project.id)
        .order_by(
            (
                func.coalesce(mat_rows.c.materials, 0)
                + func.coalesce(sub_rows.c.subs, 0)
                + func.coalesce(oth_rows.c.expenses, 0)
                + func.coalesce(adv_rows.c.advances, 0)
            ).desc()
        )
        .limit(5)
    )

    top5 = []
    for r in top5_q.all():
        top5.append(
            {
                "code": r.code,
                "name": r.name,
                "materials": float(r.materials or 0),
                "subs": float(r.subs or 0),
                "expenses": float(r.expenses or 0),
                "advances": float(r.advances or 0),
                "total": float(r.total or 0),
            }
        )

    return {
        "materials": float(materials_total),
        "subs": float(subs_payable_total),
        "expenses": float(other_total),
        "advances": float(advances_total),
        "grand": float(materials_total + subs_payable_total + other_total + advances_total),
        "other_by_category": other_by_category,
        "projects_by_status": projects_by_status,
        "top5": top5,
    }


# =========================================================
# Company profile
# =========================================================
class CompanyProfile(db.Model, TimestampMixin):
    __tablename__ = "company_profiles"

    id = db.Column(db.Integer, primary_key=True)

    company_name = db.Column(db.String(200), nullable=False, default="บริษัทของฉัน")
    tax_id = db.Column(db.String(40), nullable=True)
    address = db.Column(db.Text, nullable=True)
    phone = db.Column(db.String(80), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    website = db.Column(db.String(120), nullable=True)

    logo_path = db.Column(db.String(255), nullable=True)

    payment_bank = db.Column(db.String(200), nullable=True)
    payment_account_no = db.Column(db.String(80), nullable=True)
    payment_account_name = db.Column(db.String(200), nullable=True)
    payment_branch = db.Column(db.String(200), nullable=True)

    @staticmethod
    def get_one() -> "CompanyProfile":
        row = CompanyProfile.query.first()
        if not row:
            row = CompanyProfile()
            db.session.add(row)
            db.session.commit()
        return row


# =========================================================
# Sales docs & items
# =========================================================
class SalesDoc(db.Model, TimestampMixin):
    __tablename__ = "sales_docs"

    id = db.Column(db.Integer, primary_key=True)

    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True, index=True)
    customer = db.relationship("Customer", lazy="joined")

    doc_type = db.Column(db.String(10), nullable=False, default="QT")
    doc_no = db.Column(db.String(40), nullable=False, unique=True, index=True)
    status = db.Column(db.String(20), nullable=False, default="DRAFT")  # DRAFT/APPROVED/VOID

    issue_date = db.Column(db.Date, nullable=False, default=date.today)
    due_date = db.Column(db.Date, nullable=True)

    # Company snapshot
    company_name = db.Column(db.String(200), nullable=True)
    company_tax_id = db.Column(db.String(40), nullable=True)
    company_address = db.Column(db.Text, nullable=True)
    company_phone = db.Column(db.String(80), nullable=True)
    company_email = db.Column(db.String(120), nullable=True)
    company_website = db.Column(db.String(120), nullable=True)
    company_logo_path = db.Column(db.String(255), nullable=True)

    # Customer snapshot
    customer_name = db.Column(db.String(200), nullable=False)
    customer_tax_id = db.Column(db.String(40), nullable=True)
    customer_address = db.Column(db.Text, nullable=True)
    customer_phone = db.Column(db.String(80), nullable=True)
    customer_email = db.Column(db.String(80), nullable=True)

    subject = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)

    discount_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    vat_rate = db.Column(db.Numeric(5, 2), nullable=False, default=7)
    wht_rate = db.Column(db.Numeric(5, 2), nullable=False, default=0)

    note = db.Column(db.Text, nullable=True)

    deposit_note = db.Column(db.Text, nullable=True)
    warranty_months = db.Column(db.Integer, nullable=True)
    warranty_end_date = db.Column(db.Date, nullable=True)
    payment_terms = db.Column(db.Text, nullable=True)

    approved_by = db.Column(db.String(120), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)

    parent_id = db.Column(db.Integer, db.ForeignKey("sales_docs.id"), nullable=True, index=True)

    boq_excel_path = db.Column(db.String(255), nullable=True)
    boq_pdf_path = db.Column(db.String(255), nullable=True)

    items = db.relationship("SalesItem", backref="doc", cascade="all, delete-orphan", lazy=True)

    @staticmethod
    def _d(v) -> Decimal:
        if v is None:
            return Decimal("0")
        try:
            if isinstance(v, Decimal):
                return v
            s = str(v).strip()
            if s == "":
                return Decimal("0")
            return Decimal(s)
        except Exception:
            return Decimal("0")

    @staticmethod
    def _q2(v: Decimal) -> Decimal:
        try:
            return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except Exception:
            return v

    @property
    def subtotal(self) -> Decimal:
        total = Decimal("0")
        for it in (self.items or []):
            qty = self._d(getattr(it, "qty", 0))
            price = self._d(getattr(it, "unit_price", 0))
            disc = self._d(getattr(it, "discount_amount", 0))
            total += (qty * price) - disc
        if total < 0:
            total = Decimal("0")
        return self._q2(total)

    @property
    def discount_total(self) -> Decimal:
        v = self._d(self.discount_amount)
        if v < 0:
            v = Decimal("0")
        return self._q2(v)

    @property
    def net_before_tax(self) -> Decimal:
        v = self.subtotal - self.discount_total
        if v < 0:
            v = Decimal("0")
        return self._q2(v)

    @property
    def wht_amount(self) -> Decimal:
        rate = self._d(self.wht_rate)
        v = (self.net_before_tax * rate) / Decimal("100")
        if v < 0:
            v = Decimal("0")
        return self._q2(v)

    @property
    def net_after_wht(self) -> Decimal:
        v = self.net_before_tax - self.wht_amount
        if v < 0:
            v = Decimal("0")
        return self._q2(v)

    @property
    def vat_amount(self) -> Decimal:
        rate = self._d(self.vat_rate)
        v = (self.net_after_wht * rate) / Decimal("100")
        if v < 0:
            v = Decimal("0")
        return self._q2(v)

    @property
    def gross_total(self) -> Decimal:
        v = self.net_after_wht + self.vat_amount
        if v < 0:
            v = Decimal("0")
        return self._q2(v)

    @property
    def grand_total(self) -> Decimal:
        v = self.gross_total
        if v < 0:
            v = Decimal("0")
        return self._q2(v)

    @staticmethod
    def next_doc_no(doc_type: str = "QT") -> str:
        year = datetime.utcnow().year
        prefix = f"{doc_type}-{year}-"
        last = (
            SalesDoc.query.filter(SalesDoc.doc_type == doc_type)
            .filter(SalesDoc.doc_no.like(f"{prefix}%"))
            .order_by(SalesDoc.id.desc())
            .first()
        )
        if last and last.doc_no:
            try:
                last_no = int(last.doc_no.split("-")[-1])
            except Exception:
                last_no = 0
        else:
            last_no = 0

        return f"{prefix}{last_no + 1:04d}"


class SalesItem(db.Model, TimestampMixin):
    __tablename__ = "sales_items"

    id = db.Column(db.Integer, primary_key=True)
    doc_id = db.Column(db.Integer, db.ForeignKey("sales_docs.id"), nullable=False, index=True)

    description = db.Column(db.Text, nullable=False)
    qty = db.Column(db.Numeric(12, 2), nullable=False, default=1)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    discount_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    @property
    def line_total(self):
        try:
            return (self.qty * self.unit_price) - (self.discount_amount or 0)
        except Exception:
            return 0


# =========================================================
# ✅ Withholding master data (NEW)
# =========================================================
class WithholdingPerson(db.Model, TimestampMixin):
    """
    บุคคลธรรมดา สำหรับเอกสารหักภาษี ณ ที่จ่าย
    - person_type: EMPLOYEE / SUBCONTRACTOR
    """
    __tablename__ = "withholding_people"

    id = db.Column(db.Integer, primary_key=True)

    full_name = db.Column(db.String(200), nullable=False, index=True)
    person_type = db.Column(db.String(30), nullable=False, default="EMPLOYEE", index=True)

    # เลขบัตรประชาชน (บางกรณีอาจใช้เป็น tax_id)
    tax_id = db.Column(db.String(40), nullable=True, index=True)

    address = db.Column(db.Text, nullable=True)
    phone = db.Column(db.String(80), nullable=True)
    note = db.Column(db.Text, nullable=True)

    is_active = db.Column(db.Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_wht_people_full_name", "full_name"),
        Index("ix_wht_people_tax_id", "tax_id"),
        Index("ix_wht_people_person_type", "person_type"),
    )

    def __repr__(self) -> str:
        return f"<WithholdingPerson {self.id} {self.full_name!r}>"


class WithholdingEntity(db.Model, TimestampMixin):
    """
    นิติบุคคล สำหรับเอกสารหักภาษี ณ ที่จ่าย
    - สามารถผูกกับ Customer ได้ (customer_id)
    """
    __tablename__ = "withholding_entities"

    id = db.Column(db.Integer, primary_key=True)

    company_name = db.Column(db.String(200), nullable=False, index=True)
    tax_id = db.Column(db.String(40), nullable=True, index=True)

    address = db.Column(db.Text, nullable=True)
    phone = db.Column(db.String(80), nullable=True)
    note = db.Column(db.Text, nullable=True)

    # link to customer (optional)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True, index=True)
    customer = db.relationship("Customer", lazy="joined")

    is_active = db.Column(db.Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_wht_entities_company_name", "company_name"),
        Index("ix_wht_entities_tax_id", "tax_id"),
        Index("ix_wht_entities_customer_id", "customer_id"),
    )

    def __repr__(self) -> str:
        return f"<WithholdingEntity {self.id} {self.company_name!r}>"


# =========================
# WITHHOLDING (PND3/PND53)
# =========================
class WithholdingCertificate(db.Model, TimestampMixin):
    """
    เอกสารหนังสือรับรองหัก ณ ที่จ่าย (เริ่มที่ ภงด 3/53)
    1 ใบ = 1 รายการ (ตามที่คุณเลือก)
    """
    __tablename__ = "withholding_certificates"

    id = db.Column(db.Integer, primary_key=True)

    # PND3 / PND53
    form_type = db.Column(db.String(10), nullable=False, default="PND53", index=True)

    # เลขที่เอกสารภายในระบบ (เช่น WHT53-2026-0001)
    doc_no = db.Column(db.String(40), nullable=False, unique=True, index=True)

    # ผู้ถูกหัก: PERSON / ENTITY
    payee_kind = db.Column(db.String(10), nullable=False, default="PERSON", index=True)

    payee_person_id = db.Column(db.Integer, db.ForeignKey("withholding_people.id"), nullable=True, index=True)
    payee_entity_id = db.Column(db.Integer, db.ForeignKey("withholding_entities.id"), nullable=True, index=True)

    payee_person = db.relationship("WithholdingPerson", lazy="joined")
    payee_entity = db.relationship("WithholdingEntity", lazy="joined")

    # Snapshot ผู้จ่ายเงิน (บริษัทเรา) ตอนออกเอกสาร
    payer_name = db.Column(db.String(200), nullable=False, default="บริษัทของฉัน")
    payer_tax_id = db.Column(db.String(40), nullable=True)
    payer_address = db.Column(db.Text, nullable=True)
    payer_branch_no = db.Column(db.String(20), nullable=True, default="00000")

    # รายการจ่ายเงิน (1 รายการต่อใบ)
    payment_date = db.Column(db.Date, nullable=False, default=date.today, index=True)

    # หมวด/ประเภทเงินได้ (ใส่เป็นข้อความก่อน เดี๋ยวค่อยทำเป็นตัวเลือก)
    income_type = db.Column(db.String(120), nullable=True)   # เช่น "ค่าบริการ" / "ค่าเช่า" / ฯลฯ
    description = db.Column(db.String(255), nullable=True)   # รายละเอียดเพิ่มเติม

    base_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)  # ฐานภาษี
    wht_rate = db.Column(db.Numeric(6, 2), nullable=False, default=3)      # %
    wht_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)   # ยอดหัก

    note = db.Column(db.Text, nullable=True)

    is_active = db.Column(db.Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint(
            "(payee_kind='PERSON' AND payee_person_id IS NOT NULL AND payee_entity_id IS NULL) "
            "OR (payee_kind='ENTITY' AND payee_entity_id IS NOT NULL AND payee_person_id IS NULL)",
            name="ck_wht_cert_payee_one_of",
        ),
        CheckConstraint("base_amount >= 0", name="ck_wht_cert_base_nonneg"),
        CheckConstraint("wht_rate >= 0", name="ck_wht_cert_rate_nonneg"),
        CheckConstraint("wht_amount >= 0", name="ck_wht_cert_amount_nonneg"),
        Index("ix_wht_cert_form_type", "form_type"),
        Index("ix_wht_cert_payment_date", "payment_date"),
    )

    @property
    def payee_display_name(self) -> str:
        if self.payee_kind == "PERSON" and self.payee_person:
            return self.payee_person.full_name
        if self.payee_kind == "ENTITY" and self.payee_entity:
            return self.payee_entity.company_name
        return "-"

    @property
    def payee_tax_id(self) -> str:
        if self.payee_kind == "PERSON" and self.payee_person:
            return self.payee_person.tax_id or ""
        if self.payee_kind == "ENTITY" and self.payee_entity:
            return self.payee_entity.tax_id or ""
        return ""

    @staticmethod
    def next_doc_no(form_type: str = "PND53") -> str:
        year = datetime.utcnow().year
        prefix = "WHT53" if form_type == "PND53" else "WHT3"
        head = f"{prefix}-{year}-"
        last = (
            WithholdingCertificate.query
            .filter(WithholdingCertificate.doc_no.like(f"{head}%"))
            .order_by(WithholdingCertificate.id.desc())
            .first()
        )
        last_no = 0
        if last and last.doc_no:
            try:
                last_no = int(last.doc_no.split("-")[-1])
            except Exception:
                last_no = 0
        return f"{head}{last_no + 1:04d}"
