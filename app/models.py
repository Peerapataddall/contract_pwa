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
    # ✅ NEW: link Project <-> QT (SalesDoc)
    # - เมื่ออนุมัติ QT จะสร้าง Project และผูกด้วย sales_doc_id
    # -------------------------------------------------
    sales_doc_id = db.Column(
        db.Integer,
        db.ForeignKey("sales_docs.id"),
        nullable=True,
        unique=True,
        index=True,
    )

    # ✅ NEW: เก็บ BOQ ไว้ที่ Project ด้วย (ง่ายต่อการโชว์/ดาวน์โหลดในหน้าโครงการ)
    boq_excel_path = db.Column(db.String(255), nullable=True)
    boq_pdf_path = db.Column(db.String(255), nullable=True)

    # ความสัมพันธ์: Project.sales_doc -> SalesDoc และ SalesDoc.project -> Project (one-to-one)
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
        # จ่ายจริง = ว่าจ้าง - หัก ณ ที่จ่าย (ตามจำนวนเงินที่คีย์)
        return float(sum((s.payable_amount or 0) for s in self.subcontractors))

    @property
    def total_other_expense(self) -> float:
        return float(sum((e.amount or 0) for e in self.expenses))

    @property
    def total_cost(self) -> float:
        return float(
            self.total_material_cost + self.total_subcontractor_cost + self.total_other_expense
        )


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
    materials_total = (
        db.session.query(func.coalesce(func.sum(MaterialItem.unit_price * MaterialItem.qty), 0))
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
        .scalar()
        or 0
    )
    other_total = (
        db.session.query(func.coalesce(func.sum(OtherExpense.amount), 0)).scalar() or 0
    )

    # หมวดค่าใช้จ่ายอื่นๆ แยกตาม category
    rows = (
        db.session.query(OtherExpense.category, func.coalesce(func.sum(OtherExpense.amount), 0))
        .group_by(OtherExpense.category)
        .order_by(func.sum(OtherExpense.amount).desc())
        .all()
    )
    other_by_category = [{"category": c, "total": float(t)} for c, t in rows]

    # นับสถานะโครงการ
    status_rows = db.session.query(Project.status, func.count(Project.id)).group_by(Project.status).all()
    projects_by_status = {s: int(n) for s, n in status_rows}

    return {
        "materials_total": float(materials_total),
        "subcontractors_total": float(subs_payable_total),
        "other_total": float(other_total),
        "grand_total": float(materials_total + subs_payable_total + other_total),
        "other_by_category": other_by_category,
        "projects_by_status": projects_by_status,
    }


class CompanyProfile(db.Model, TimestampMixin):
    __tablename__ = "company_profiles"

    id = db.Column(db.Integer, primary_key=True)

    company_name = db.Column(db.String(200), nullable=False, default="บริษัทของฉัน")
    tax_id = db.Column(db.String(40), nullable=True)
    address = db.Column(db.Text, nullable=True)
    phone = db.Column(db.String(80), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    website = db.Column(db.String(120), nullable=True)

    # เก็บ path โลโก้ (ไฟล์อยู่ใน static/uploads/...)
    logo_path = db.Column(db.String(255), nullable=True)

    # -------------------------
    # ข้อมูลการชำระเงิน (ใช้ตอนพิมพ์ใบเสนอราคา)
    # -------------------------
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


class SalesDoc(db.Model, TimestampMixin):
    __tablename__ = "sales_docs"

    id = db.Column(db.Integer, primary_key=True)

    # -------------------------
    # Customer master reference
    # -------------------------
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True, index=True)
    customer = db.relationship("Customer", lazy="joined")


    # QT/BL/IV/RC
    doc_type = db.Column(db.String(10), nullable=False, default="QT")

    # เลขเอกสาร เช่น QT-2026-0001
    doc_no = db.Column(db.String(40), nullable=False, unique=True, index=True)

    # สถานะเริ่มต้น
    status = db.Column(db.String(20), nullable=False, default="DRAFT")  # DRAFT/APPROVED/VOID

    # ✅ db.Date ควรใช้ date.today ไม่ใช่ datetime.utcnow
    issue_date = db.Column(db.Date, nullable=False, default=date.today)
    due_date = db.Column(db.Date, nullable=True)

    # ----- ข้อมูลบริษัท (snapshot) -----
    company_name = db.Column(db.String(200), nullable=True)
    company_tax_id = db.Column(db.String(40), nullable=True)
    company_address = db.Column(db.Text, nullable=True)
    company_phone = db.Column(db.String(80), nullable=True)
    company_email = db.Column(db.String(120), nullable=True)
    company_website = db.Column(db.String(120), nullable=True)
    company_logo_path = db.Column(db.String(255), nullable=True)

    # ----- ข้อมูลลูกค้า -----
    customer_name = db.Column(db.String(200), nullable=False)
    customer_tax_id = db.Column(db.String(40), nullable=True)
    customer_address = db.Column(db.Text, nullable=True)
    customer_phone = db.Column(db.String(80), nullable=True)
    customer_email = db.Column(db.String(120), nullable=True)

    # หัวเรื่อง/รายละเอียดงาน
    subject = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)

    # ส่วนลดระดับเอกสาร
    discount_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    # VAT/WHT
    vat_rate = db.Column(db.Numeric(5, 2), nullable=False, default=7)  # %
    wht_rate = db.Column(db.Numeric(5, 2), nullable=False, default=0)  # %

    note = db.Column(db.Text, nullable=True)

    # เงื่อนไขเงินประกัน + ระยะเวลารับประกัน (เดือน) + เงื่อนไขชำระเงิน
    deposit_note = db.Column(db.Text, nullable=True)
    warranty_months = db.Column(db.Integer, nullable=True)
    payment_terms = db.Column(db.Text, nullable=True)

    # อนุมัติ
    approved_by = db.Column(db.String(120), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)

    # สำหรับเอกสารลูก (IV/RC/BL อ้างอิง QT)
    parent_id = db.Column(db.Integer, db.ForeignKey("sales_docs.id"), nullable=True, index=True)

    # ✅ แนบไฟล์ BOQ
    boq_excel_path = db.Column(db.String(255), nullable=True)
    boq_pdf_path = db.Column(db.String(255), nullable=True)

    items = db.relationship("SalesItem", backref="doc", cascade="all, delete-orphan", lazy=True)

    # -----------------------------
    # ✅ Helpers + Totals (คำนวณยอด)
    # -----------------------------
    @staticmethod
    def _d(v) -> Decimal:
        """Convert value to Decimal safely."""
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
        """Quantize to 2 decimals."""
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
        """
        ✅ WHT ต้องถูกคิดก่อน VAT (ตามที่ต้องการ)
        - base = net_before_tax (หลังส่วนลดท้ายบิล)
        - wht_amount = base * wht_rate
        """
        rate = self._d(self.wht_rate)
        v = (self.net_before_tax * rate) / Decimal("100")
        if v < 0:
            v = Decimal("0")
        return self._q2(v)

    @property
    def net_after_wht(self) -> Decimal:
        """
        ยอดหลังหัก ณ ที่จ่าย (ฐานสำหรับคิด VAT)
        """
        v = self.net_before_tax - self.wht_amount
        if v < 0:
            v = Decimal("0")
        return self._q2(v)

    @property
    def vat_amount(self) -> Decimal:
        """
        ✅ VAT คิดจากยอดหลังหัก ณ ที่จ่าย (net_after_wht)
        """
        rate = self._d(self.vat_rate)
        v = (self.net_after_wht * rate) / Decimal("100")
        if v < 0:
            v = Decimal("0")
        return self._q2(v)

    @property
    def gross_total(self) -> Decimal:
        """
        จำนวนเงินรวมทั้งสิ้น (หลังหัก ณ ที่จ่าย แล้วบวก VAT)
        """
        v = self.net_after_wht + self.vat_amount
        if v < 0:
            v = Decimal("0")
        return self._q2(v)

    @property
    def grand_total(self) -> Decimal:
        """
        ยอดชำระ = gross_total (เพราะหัก ณ ที่จ่ายไปแล้วก่อนคิด VAT)
        """
        v = self.gross_total
        if v < 0:
            v = Decimal("0")
        return self._q2(v)

    # -----------------------------
    # ✅ Doc No generator
    # -----------------------------
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
