from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import joinedload

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from werkzeug.utils import secure_filename

from .. import db
from ..models import CompanyProfile, Customer, Project, SalesDoc, SalesItem

bp_docs = Blueprint("docs", __name__)

# -------------------------------------------------
# Config
# -------------------------------------------------
ALLOWED_BOQ_EXT = {"xls", "xlsx", "pdf"}

DOC_TITLE = {
    "QT": "ใบเสนอราคา",
    "IV": "ใบกำกับภาษี",
    "RC": "ใบเสร็จรับเงิน",
    "BL": "ใบวางบิล/แจ้งหนี้",
}


# -------------------------------------------------
# Helpers
# -------------------------------------------------
def _to_decimal(v, default="0"):
    try:
        s = (v or "").strip()
        if s == "":
            return Decimal(default)
        return Decimal(s)
    except Exception:
        return Decimal(default)


def _today() -> date:
    return date.today()


def _allowed_file(filename: str, allowed_ext: set[str]) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_ext


def _save_boq_file(file_storage, subdir: str, allowed_ext: set[str]) -> str | None:
    """
    save BOQ file to static/uploads/boq/<subdir>/
    return relative path (ex: uploads/boq/excel/<uuid>.xlsx) or None
    """
    if not file_storage or not getattr(file_storage, "filename", ""):
        return None

    filename = (file_storage.filename or "").strip()
    if filename == "":
        return None

    if not _allowed_file(filename, allowed_ext):
        return None

    ext = filename.rsplit(".", 1)[1].lower()
    fname = secure_filename(f"{uuid4().hex}.{ext}")

    base_dir = os.path.join(current_app.root_path, "static", "uploads", "boq", subdir)
    os.makedirs(base_dir, exist_ok=True)

    full_path = os.path.join(base_dir, fname)
    file_storage.save(full_path)

    return f"uploads/boq/{subdir}/{fname}"


def _snapshot_company_to_doc(doc: SalesDoc):
    cp = CompanyProfile.query.first()
    if not cp:
        return
    doc.company_name = getattr(cp, "company_name", None)
    doc.company_tax_id = getattr(cp, "tax_id", None)
    doc.company_address = getattr(cp, "address", None)
    doc.company_phone = getattr(cp, "phone", None)
    doc.company_email = getattr(cp, "email", None)
    doc.company_website = getattr(cp, "website", None)
    doc.company_logo_path = getattr(cp, "logo_path", None)


def _clone_child_from_parent(parent: SalesDoc, child_type: str) -> SalesDoc:
    child_type = (child_type or "").upper().strip()
    if child_type not in ("IV", "RC", "BL"):
        abort(404)

    child = SalesDoc(
        doc_type=child_type,
        doc_no=SalesDoc.next_doc_no(child_type),
        status="DRAFT",
        issue_date=_today(),
        due_date=parent.due_date,
        parent_id=parent.id,
        company_name=parent.company_name,
        company_tax_id=parent.company_tax_id,
        company_address=parent.company_address,
        company_phone=parent.company_phone,
        company_email=parent.company_email,
        company_website=parent.company_website,
        company_logo_path=parent.company_logo_path,
        customer_name=parent.customer_name,
        customer_tax_id=parent.customer_tax_id,
        customer_address=parent.customer_address,
        customer_phone=parent.customer_phone,
        customer_email=parent.customer_email,
        subject=parent.subject,
        description=parent.description,
        note=parent.note,
        discount_amount=parent.discount_amount,
        vat_rate=parent.vat_rate,
        wht_rate=parent.wht_rate,
    )

    # เอกสารลูกไม่ต้องถือ BOQ (ตามโจทย์: แนบที่ QT)
    child.boq_excel_path = None
    child.boq_pdf_path = None

    # ถ้า QT เดิมไม่มี snapshot บริษัท ให้ fallback
    if not (child.company_name or "").strip():
        _snapshot_company_to_doc(child)

    for it in (parent.items or []):
        child.items.append(
            SalesItem(
                description=it.description,
                qty=it.qty,
                unit_price=it.unit_price,
                discount_amount=it.discount_amount,
            )
        )

    return child


def _boq_abs_path(rel_path: str) -> str | None:
    """
    rel_path like 'uploads/boq/excel/xxxx.xlsx' (stored in DB)
    return absolute path under static or None if unsafe
    """
    if not rel_path:
        return None
    rel_path = rel_path.replace("\\", "/").lstrip("/")
    if not rel_path.startswith("uploads/boq/"):
        return None
    return os.path.join(current_app.root_path, "static", rel_path)


def _ensure_project_from_qt(doc: SalesDoc) -> Project | None:
    """
    ✅ สร้างโครงการจาก QT (เมื่ออนุมัติ)
    - code ใช้ doc.doc_no เพื่อไม่ต้องเดา pattern และกันซ้ำง่าย
    - name ใช้ subject (ถ้าว่าง fallback เป็น "โครงการ <doc_no>")
    - โยก BOQ path ไปไว้ที่ Project ด้วย
    """
    if not doc or doc.doc_type != "QT":
        return None

    # ถ้ามีแล้วไม่สร้างซ้ำ
    existing = Project.query.filter(Project.sales_doc_id == doc.id).first()
    if existing:
        return existing

    code = (doc.doc_no or "").strip() or f"QT-{doc.id}"
    name = (doc.subject or "").strip() or f"โครงการ {code}"

    p = Project(
        code=code,
        name=name,
        description=(doc.description or None),
        customer_name=(doc.customer_name or None),
        status="IN_PROGRESS",
        work_days=0,
        sales_doc_id=doc.id,
        boq_excel_path=getattr(doc, "boq_excel_path", None),
        boq_pdf_path=getattr(doc, "boq_pdf_path", None),
    )
    db.session.add(p)
    return p


# -------------------------------------------------
# Routes
# -------------------------------------------------
@bp_docs.get("/docs")
def docs_list():
    q = (request.args.get("q") or "").strip()
    doc_type = (request.args.get("type") or "QT").upper().strip()
    status = (request.args.get("status") or "").upper().strip()

    if doc_type not in ("QT", "IV", "RC", "BL"):
        doc_type = "QT"

    query = SalesDoc.query.filter(SalesDoc.doc_type == doc_type)

    if q:
        like = f"%{q}%"
        query = query.filter(
            (SalesDoc.doc_no.ilike(like))
            | (SalesDoc.customer_name.ilike(like))
            | (SalesDoc.subject.ilike(like))
        )

    if status:
        query = query.filter(SalesDoc.status == status)

    docs = query.order_by(SalesDoc.id.desc()).all()
    return render_template(
        "docs/list.html",
        docs=docs,
        q=q,
        doc_type=doc_type,
        status=status,
        DOC_TITLE=DOC_TITLE,
    )


@bp_docs.get("/docs/qt/new")
def qt_new():
    return render_template(
        "docs/form_qt.html",
        doc=None,
        doc_no=SalesDoc.next_doc_no("QT"),
        today=_today(),
        items=[{"description": "", "qty": "1", "unit_price": "0", "discount_amount": "0"}],
    )


@bp_docs.post("/docs/qt/new")
def qt_create():
    # เลือกจากฐานข้อมูลลูกค้า (Customer master) ได้
    customer_id_raw = (request.form.get("customer_id") or "").strip()
    customer = None
    if customer_id_raw.isdigit():
        customer = Customer.query.get(int(customer_id_raw))

    customer_name = (request.form.get("customer_name") or "").strip()
    if customer and not customer_name:
        customer_name = customer.name

    if not customer_name:
        flash("กรุณากรอกชื่อลูกค้า หรือเลือกจากรายการลูกค้า", "error")
        return redirect(url_for("docs.qt_new"))

    doc_no = (request.form.get("doc_no") or "").strip() or SalesDoc.next_doc_no("QT")

    doc = SalesDoc(
        doc_type="QT",
        doc_no=doc_no,
        status="DRAFT",
        issue_date=_today(),
        customer_name=customer_name,
        customer_tax_id=(request.form.get("customer_tax_id") or "").strip() or None,
        customer_address=(request.form.get("customer_address") or "").strip() or None,
        customer_phone=(request.form.get("customer_phone") or "").strip() or None,
        customer_email=(request.form.get("customer_email") or "").strip() or None,
        subject=(request.form.get("subject") or "").strip() or None,
        description=(request.form.get("description") or "").strip() or None,
        note=(request.form.get("note") or "").strip() or None,
        deposit_note=(request.form.get("deposit_note") or "").strip() or None,
        payment_terms=(request.form.get("payment_terms") or "").strip() or None,
        discount_amount=_to_decimal(request.form.get("discount_amount"), "0"),
        vat_rate=_to_decimal(request.form.get("vat_rate"), "7"),
        wht_rate=_to_decimal(request.form.get("wht_rate"), "0"),
    )

    # ผูก customer_id ถ้ามี (ไม่ทำ snapshot แยกต่างหาก)
    if customer:
        doc.customer_id = customer.id
        # เพื่อความเข้ากันได้กับฟิลด์เดิมของเอกสาร: ถ้าผู้ใช้ไม่ได้กรอก ให้เติมจากฐานลูกค้า
        if not doc.customer_tax_id:
            doc.customer_tax_id = customer.tax_id
        if not doc.customer_address:
            doc.customer_address = customer.address
        if not doc.customer_phone:
            doc.customer_phone = customer.phone
        if not doc.customer_email:
            doc.customer_email = customer.email


    w = (request.form.get("warranty_months") or "").strip()
    doc.warranty_months = int(w) if w.isdigit() else None

    _snapshot_company_to_doc(doc)

    # -------------------------
    # BOQ Upload (Excel + PDF)
    # -------------------------
    # หมายเหตุ: ต้องมี enctype="multipart/form-data" ใน form_qt.html
    boq_excel = request.files.get("boq_excel")
    boq_pdf = request.files.get("boq_pdf")

    excel_path = _save_boq_file(boq_excel, "excel", {"xls", "xlsx"})
    pdf_path = _save_boq_file(boq_pdf, "pdf", {"pdf"})

    if boq_excel and boq_excel.filename and excel_path is None:
        flash("ไฟล์ BOQ (Excel) รองรับเฉพาะ .xls / .xlsx", "error")
        return redirect(url_for("docs.qt_new"))

    if boq_pdf and boq_pdf.filename and pdf_path is None:
        flash("ไฟล์ BOQ (PDF) รองรับเฉพาะ .pdf", "error")
        return redirect(url_for("docs.qt_new"))

    doc.boq_excel_path = excel_path
    doc.boq_pdf_path = pdf_path

    # -------------------------
    # Items
    # -------------------------
    descriptions = request.form.getlist("item_description")
    qtys = request.form.getlist("item_qty")
    prices = request.form.getlist("item_unit_price")
    discounts = request.form.getlist("item_discount_amount")

    for i in range(max(len(descriptions), len(qtys), len(prices), len(discounts))):
        desc = (descriptions[i] if i < len(descriptions) else "") or ""
        desc = desc.strip()
        if not desc:
            continue

        qty = qtys[i] if i < len(qtys) else "1"
        price = prices[i] if i < len(prices) else "0"
        disc = discounts[i] if i < len(discounts) else "0"

        doc.items.append(
            SalesItem(
                description=desc,
                qty=_to_decimal(qty, "1"),
                unit_price=_to_decimal(price, "0"),
                discount_amount=_to_decimal(disc, "0"),
            )
        )

    if not doc.items:
        flash("กรุณาใส่อย่างน้อย 1 รายการ", "error")
        return redirect(url_for("docs.qt_new"))

    db.session.add(doc)
    db.session.commit()

    flash(f"สร้างใบเสนอราคา {doc.doc_no} เรียบร้อย", "success")
    return redirect(url_for("docs.doc_view", doc_id=doc.id))


@bp_docs.get("/docs/<int:doc_id>")
def doc_view(doc_id: int):
    doc = SalesDoc.query.options(joinedload(SalesDoc.customer)).get_or_404(doc_id)

    children = []
    if doc.doc_type == "QT":
        children = SalesDoc.query.filter_by(parent_id=doc.id).order_by(SalesDoc.id.asc()).all()

    return render_template(
        "docs/view.html",
        doc=doc,
        children=children,
        DOC_TITLE=DOC_TITLE,
    )


@bp_docs.post("/docs/<int:doc_id>/approve")
def doc_approve(doc_id: int):
    doc = SalesDoc.query.options(joinedload(SalesDoc.customer)).get_or_404(doc_id)

    if doc.status != "APPROVED":
        doc.status = "APPROVED"
        doc.approved_by = (request.form.get("approved_by") or "").strip() or "ADMIN"
        doc.approved_at = datetime.utcnow()

        # ✅ NEW: อนุมัติ QT แล้วสร้างโครงการอัตโนมัติ (ผูก sales_doc_id)
        if doc.doc_type == "QT":
            _ensure_project_from_qt(doc)

        db.session.commit()
        flash("อนุมัติเอกสารแล้ว", "success")

    return redirect(url_for("docs.doc_view", doc_id=doc.id))


@bp_docs.post("/docs/<int:doc_id>/create/<string:child_type>")
def doc_create_child(doc_id: int, child_type: str):
    child_type = (child_type or "").upper().strip()
    if child_type not in ("IV", "RC", "BL"):
        abort(404)

    parent = SalesDoc.query.get_or_404(doc_id)

    if parent.doc_type != "QT":
        flash("สร้างเอกสารถัดไปได้เฉพาะจากใบเสนอราคา (QT) เท่านั้น", "error")
        return redirect(url_for("docs.doc_view", doc_id=parent.id))

    if parent.status != "APPROVED":
        flash("ต้องอนุมัติใบเสนอราคา (QT) ก่อน ถึงจะสร้างเอกสารถัดไปได้", "error")
        return redirect(url_for("docs.doc_view", doc_id=parent.id))

    existing = SalesDoc.query.filter_by(parent_id=parent.id, doc_type=child_type).first()
    if existing:
        flash(f"{DOC_TITLE.get(child_type, child_type)} ถูกสร้างไว้แล้ว", "info")
        return redirect(url_for("docs.doc_view", doc_id=existing.id))

    child = _clone_child_from_parent(parent, child_type)
    db.session.add(child)
    db.session.commit()

    flash(f"สร้าง {DOC_TITLE.get(child_type, child_type)} {child.doc_no} เรียบร้อย", "success")
    return redirect(url_for("docs.doc_view", doc_id=child.id))


@bp_docs.get("/docs/<int:doc_id>/print")
def doc_print(doc_id: int):
    doc = SalesDoc.query.options(joinedload(SalesDoc.customer)).get_or_404(doc_id)
    company = CompanyProfile.query.first()
    return render_template(
        "docs/print_doc.html",
        doc=doc,
        company=company,
        DOC_TITLE=DOC_TITLE,
    )


# -------------------------------------------------
# ✅ Download BOQ (Excel / PDF) (ที่หน้าเอกสาร)
# -------------------------------------------------
@bp_docs.get("/docs/<int:doc_id>/boq/excel")
def doc_download_boq_excel(doc_id: int):
    doc = SalesDoc.query.options(joinedload(SalesDoc.customer)).get_or_404(doc_id)
    if doc.doc_type != "QT":
        abort(404)

    rel = getattr(doc, "boq_excel_path", None) or ""
    abs_path = _boq_abs_path(rel)
    if not abs_path or not os.path.exists(abs_path):
        flash("ไม่พบไฟล์ BOQ (Excel)", "error")
        return redirect(url_for("docs.doc_view", doc_id=doc.id))

    directory = os.path.dirname(abs_path)
    filename = os.path.basename(abs_path)
    return send_from_directory(directory, filename, as_attachment=True)


@bp_docs.get("/docs/<int:doc_id>/boq/pdf")
def doc_download_boq_pdf(doc_id: int):
    doc = SalesDoc.query.options(joinedload(SalesDoc.customer)).get_or_404(doc_id)
    if doc.doc_type != "QT":
        abort(404)

    rel = getattr(doc, "boq_pdf_path", None) or ""
    abs_path = _boq_abs_path(rel)
    if not abs_path or not os.path.exists(abs_path):
        flash("ไม่พบไฟล์ BOQ (PDF)", "error")
        return redirect(url_for("docs.doc_view", doc_id=doc.id))

    directory = os.path.dirname(abs_path)
    filename = os.path.basename(abs_path)
    return send_from_directory(directory, filename, as_attachment=True)
