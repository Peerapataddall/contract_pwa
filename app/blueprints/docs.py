from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

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
from ..models import CompanyProfile, Customer, Project, SalesDoc, SalesInstallment, SalesItem

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

DOC_STATUS_BY_TYPE = {
    "QT": {
        "draft": "ฉบับร่าง",
        "approved": "อนุมัติแล้ว",
        "cancelled": "ยกเลิก",
    },
    "BL": {
        "draft": "ฉบับร่าง",
        "approved": "วางบิลแล้ว",
        "cancelled": "ยกเลิก",
    },
    "IV": {
        "draft": "ฉบับร่าง",
        "approved": "ออกแล้ว",
        "cancelled": "ยกเลิก",
    },
    "RC": {
        "draft": "ฉบับร่าง",
        "approved": "รับชำระแล้ว",
        "cancelled": "ยกเลิก",
    },
}

OLD_TO_THAI_STATUS = {
    "DRAFT": "ฉบับร่าง",
    "APPROVED": "อนุมัติแล้ว",
    "BILLED": "วางบิลแล้ว",
    "ISSUED": "ออกแล้ว",
    "PAID": "รับชำระแล้ว",
    "CANCELLED": "ยกเลิก",
}

INSTALLMENT_STATUS = {
    "new": "ยังไม่วางบิล",
    "billed": "วางบิลแล้ว",
    "invoiced": "ออกใบกำกับภาษีแล้ว",
    "received": "รับชำระแล้ว",
    "overdue": "เกินกำหนด",
    "cancelled": "ยกเลิก",
}


# -------------------------------------------------
# Helpers
# -------------------------------------------------
def _to_decimal(v, default="0"):
    try:
        s = str(v or "").strip().replace(",", "")
        if s == "":
            return Decimal(default)
        return Decimal(s)
    except Exception:
        return Decimal(default)


def _q2(v: Decimal) -> Decimal:
    try:
        return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return v


def _today() -> date:
    return date.today()


def _normalize_status(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    upper = raw.upper()
    return OLD_TO_THAI_STATUS.get(upper, raw)


def _doc_status(doc_type: str, key: str) -> str:
    dt = (doc_type or "QT").upper().strip()
    row = DOC_STATUS_BY_TYPE.get(dt, DOC_STATUS_BY_TYPE["QT"])
    return row.get(key, row["draft"])


def _is_doc_status(doc: SalesDoc, key: str) -> bool:
    current = _normalize_status(getattr(doc, "status", "") or "")
    dt = (doc.doc_type or "QT").upper().strip()
    expected = _doc_status(dt, key)
    if current == expected:
        return True

    # backward compat
    if key == "draft" and (getattr(doc, "status", "") or "").upper() == "DRAFT":
        return True
    if key == "approved" and (getattr(doc, "status", "") or "").upper() == "APPROVED":
        return True

    return False


def _allowed_file(filename: str, allowed_ext: set[str]) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_ext


def _unique_filename(base_dir: str, original_filename: str) -> str:
    """
    ใช้ชื่อไฟล์เดิมของผู้ใช้เป็นหลัก
    ถ้าชื่อซ้ำในโฟลเดอร์ ให้เติม _1, _2, ...
    """
    safe_name = secure_filename((original_filename or "").strip())
    if not safe_name:
        safe_name = "file"

    name, ext = os.path.splitext(safe_name)
    candidate = safe_name
    counter = 1

    while os.path.exists(os.path.join(base_dir, candidate)):
        candidate = f"{name}_{counter}{ext}"
        counter += 1

    return candidate


def _save_boq_file(file_storage, subdir: str, allowed_ext: set[str]) -> str | None:
    """
    save BOQ file to static/uploads/boq/<subdir>/
    return relative path (ex: uploads/boq/excel/my_boq.xlsx) or None
    """
    if not file_storage or not getattr(file_storage, "filename", ""):
        return None

    filename = (file_storage.filename or "").strip()
    if filename == "":
        return None

    if not _allowed_file(filename, allowed_ext):
        return None

    base_dir = os.path.join(current_app.root_path, "static", "uploads", "boq", subdir)
    os.makedirs(base_dir, exist_ok=True)

    final_name = _unique_filename(base_dir, filename)
    full_path = os.path.join(base_dir, final_name)
    file_storage.save(full_path)

    return f"uploads/boq/{subdir}/{final_name}"


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


def _boq_download_name(rel_path: str, fallback_prefix: str = "boq") -> str:
    """
    แปลงชื่อไฟล์จาก path ที่เก็บใน DB ไปเป็นชื่อดาวน์โหลด
    """
    if not rel_path:
        return fallback_prefix

    rel_path = rel_path.replace("\\", "/").strip()
    filename = os.path.basename(rel_path)
    if not filename:
        return fallback_prefix

    safe_name = secure_filename(filename)
    return safe_name or fallback_prefix


def _ensure_project_from_qt(doc: SalesDoc) -> Project | None:
    """
    สร้างโครงการจาก QT เมื่ออนุมัติ
    """
    if not doc or doc.doc_type != "QT":
        return None

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


def _parse_date_yyyy_mm_dd(x: str | None):
    try:
        s = (x or "").strip()
        if not s:
            return None
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _parse_date_dd_mm_yyyy(x: str | None):
    try:
        s = (x or "").strip()
        if not s:
            return None
        return datetime.strptime(s, "%d/%m/%Y").date()
    except Exception:
        return None


def _parse_any_date(x: str | None):
    return _parse_date_yyyy_mm_dd(x) or _parse_date_dd_mm_yyyy(x)


def _installments_locked(doc: SalesDoc) -> bool:
    if not doc or (doc.doc_type or "").upper() != "QT":
        return True

    for inst in (doc.installments or []):
        if inst.is_locked:
            return True
    return False


def _sync_installment_status(inst: SalesInstallment):
    now = datetime.utcnow()

    billed_ok = False
    invoiced_ok = False
    received_ok = False

    if inst.billing_doc:
        billed_ok = _is_doc_status(inst.billing_doc, "approved")
    if inst.invoice_doc:
        invoiced_ok = _is_doc_status(inst.invoice_doc, "approved")
    if inst.receipt_doc:
        received_ok = _is_doc_status(inst.receipt_doc, "approved")

    if received_ok:
        inst.status = INSTALLMENT_STATUS["received"]
        if not inst.received_at:
            inst.received_at = now
        if not inst.invoiced_at:
            inst.invoiced_at = now
        if not inst.billed_at:
            inst.billed_at = now
        return

    if invoiced_ok:
        inst.status = INSTALLMENT_STATUS["invoiced"]
        if not inst.invoiced_at:
            inst.invoiced_at = now
        if not inst.billed_at:
            inst.billed_at = now
        return

    if billed_ok:
        inst.status = INSTALLMENT_STATUS["billed"]
        if not inst.billed_at:
            inst.billed_at = now
        return

    if inst.due_date and inst.due_date < _today():
        inst.status = INSTALLMENT_STATUS["overdue"]
        return

    inst.status = INSTALLMENT_STATUS["new"]


def _build_single_installment_from_quote(doc: SalesDoc) -> SalesInstallment:
    inst = SalesInstallment(
        quote_id=doc.id,
        installment_no=1,
        title="งวดที่ 1",
        percent=Decimal("100.00"),
        amount_before_tax=doc.net_before_tax,
        vat_amount=doc.vat_amount,
        wht_amount=doc.wht_amount,
        gross_total=doc.gross_total,
        net_total=doc.grand_total,
        due_date=doc.due_date,
        status=INSTALLMENT_STATUS["new"],
    )
    return inst


def _parse_installment_rows_from_form():
    titles = request.form.getlist("installment_title")
    percents = request.form.getlist("installment_percent")
    due_dates = request.form.getlist("installment_due_date")
    remarks = request.form.getlist("installment_remark")

    max_len = max(len(titles), len(percents), len(due_dates), len(remarks), 0)
    rows = []

    for i in range(max_len):
        title = (titles[i] if i < len(titles) else "").strip()
        percent = _to_decimal(percents[i] if i < len(percents) else "0", "0")
        due_date = _parse_any_date(due_dates[i] if i < len(due_dates) else "")
        remark = (remarks[i] if i < len(remarks) else "").strip()

        if title == "" and percent == 0 and due_date is None and remark == "":
            continue

        rows.append(
            {
                "title": title or f"งวดที่ {len(rows) + 1}",
                "percent": percent,
                "due_date": due_date,
                "remark": remark or None,
            }
        )

    return rows


def _replace_installments_from_rows(doc: SalesDoc, rows: list[dict]):
    """
    rows ต้องมี percent เป็นหลัก
    ใช้ QT เป็นเอกสารแม่ คำนวณงวดจากฐานก่อน VAT
    งวดสุดท้ายรับเศษปัดทศนิยม
    """
    if not doc or (doc.doc_type or "").upper() != "QT":
        raise ValueError("รองรับเฉพาะ QT")

    if _installments_locked(doc):
        raise ValueError("งวดนี้มีเอกสารถูกสร้างแล้ว ไม่สามารถแก้ไขแผนงวดได้")

    if not rows:
        doc.installments.clear()
        return

    total_percent = Decimal("0")
    cleaned = []
    for idx, row in enumerate(rows, start=1):
        pct = _to_decimal(row.get("percent"), "0")
        if pct <= 0:
            continue
        total_percent += pct
        cleaned.append(
            {
                "installment_no": len(cleaned) + 1,
                "title": (row.get("title") or f"งวดที่ {idx}").strip(),
                "percent": pct,
                "due_date": row.get("due_date"),
                "remark": row.get("remark"),
            }
        )

    if not cleaned:
        doc.installments.clear()
        return

    if _q2(total_percent) != Decimal("100.00"):
        raise ValueError("ผลรวมเปอร์เซ็นต์ของทุกงวดต้องเท่ากับ 100%")

    base_total = _q2(doc.net_before_tax)
    vat_total = _q2(doc.vat_amount)
    wht_total = _q2(doc.wht_amount)
    gross_total = _q2(doc.gross_total)
    net_total = _q2(doc.grand_total)

    remaining_base = base_total
    remaining_vat = vat_total
    remaining_wht = wht_total
    remaining_gross = gross_total
    remaining_net = net_total

    doc.installments.clear()

    for idx, row in enumerate(cleaned, start=1):
        pct = _to_decimal(row["percent"], "0")

        if idx < len(cleaned):
            base_amt = _q2((base_total * pct) / Decimal("100"))
            vat_amt = _q2((vat_total * pct) / Decimal("100"))
            wht_amt = _q2((wht_total * pct) / Decimal("100"))
            gross_amt = _q2((gross_total * pct) / Decimal("100"))
            net_amt = _q2((net_total * pct) / Decimal("100"))
        else:
            base_amt = remaining_base
            vat_amt = remaining_vat
            wht_amt = remaining_wht
            gross_amt = remaining_gross
            net_amt = remaining_net

        remaining_base = _q2(remaining_base - base_amt)
        remaining_vat = _q2(remaining_vat - vat_amt)
        remaining_wht = _q2(remaining_wht - wht_amt)
        remaining_gross = _q2(remaining_gross - gross_amt)
        remaining_net = _q2(remaining_net - net_amt)

        inst = SalesInstallment(
            quote_id=doc.id,
            installment_no=idx,
            title=row["title"] or f"งวดที่ {idx}",
            percent=pct,
            amount_before_tax=base_amt,
            vat_amount=vat_amt,
            wht_amount=wht_amt,
            gross_total=gross_amt,
            net_total=net_amt,
            due_date=row.get("due_date"),
            status=INSTALLMENT_STATUS["new"],
            remark=row.get("remark"),
        )
        _sync_installment_status(inst)
        doc.installments.append(inst)


def _upsert_installments_from_request(doc: SalesDoc):
    rows = _parse_installment_rows_from_form()
    if rows:
        _replace_installments_from_rows(doc, rows)
    else:
        # ถ้าไม่มีฟิลด์งวดมาเลย ให้คงของเดิมไว้
        pass


def _clone_child_from_installment(parent: SalesDoc, installment: SalesInstallment, child_type: str) -> SalesDoc:
    child_type = (child_type or "").upper().strip()
    if child_type not in ("IV", "RC", "BL"):
        abort(404)

    child = SalesDoc(
        doc_type=child_type,
        doc_no=SalesDoc.next_doc_no(child_type),
        status=_doc_status(child_type, "draft"),
        issue_date=_today(),
        due_date=installment.due_date or parent.due_date,
        parent_id=parent.id,
        installment_id=installment.id,
        company_name=parent.company_name,
        company_tax_id=parent.company_tax_id,
        company_address=parent.company_address,
        company_phone=parent.company_phone,
        company_email=parent.company_email,
        company_website=parent.company_website,
        company_logo_path=parent.company_logo_path,
        customer_id=parent.customer_id,
        customer_name=parent.customer_name,
        customer_tax_id=parent.customer_tax_id,
        customer_address=parent.customer_address,
        customer_phone=parent.customer_phone,
        customer_email=parent.customer_email,
        subject=parent.subject,
        description=installment.line_description,
        note=parent.note,
        deposit_note=parent.deposit_note,
        payment_terms=parent.payment_terms,
        warranty_months=parent.warranty_months,
        warranty_end_date=parent.warranty_end_date,
        discount_amount=Decimal("0"),
        vat_rate=parent.vat_rate,
        wht_rate=parent.wht_rate,
    )

    # เอกสารลูกไม่ต้องถือ BOQ (แนบไว้ที่ QT)
    child.boq_excel_path = None
    child.boq_pdf_path = None

    if not (child.company_name or "").strip():
        _snapshot_company_to_doc(child)

    child.items.append(
        SalesItem(
            description=installment.line_description,
            qty=Decimal("1"),
            unit_price=_to_decimal(installment.amount_before_tax, "0"),
            discount_amount=Decimal("0"),
        )
    )

    return child


def _clone_child_from_parent(parent: SalesDoc, child_type: str) -> SalesDoc:
    """
    backward compatible:
    - ถ้า QT ไม่มีงวดเลย -> สร้างงวด 100% แล้วค่อยออกเอกสารลูกจากงวด
    """
    if (parent.doc_type or "").upper() != "QT":
        abort(404)

    if parent.installments:
        inst = parent.installments[0]
    else:
        inst = _build_single_installment_from_quote(parent)
        parent.installments.append(inst)
        db.session.flush()

    return _clone_child_from_installment(parent, inst, child_type)


def _boq_has_any_upload(doc: SalesDoc) -> bool:
    return bool((doc.boq_excel_path or "").strip() or (doc.boq_pdf_path or "").strip())


# -------------------------------------------------
# Routes
# -------------------------------------------------
@bp_docs.get("/docs")
def docs_list():
    q = (request.args.get("q") or "").strip()
    doc_type = (request.args.get("type") or "QT").upper().strip()
    status = _normalize_status(request.args.get("status") or "")

    if doc_type not in ("QT", "IV", "RC", "BL"):
        doc_type = "QT"

    query = SalesDoc.query.filter(SalesDoc.doc_type == doc_type)

    if q:
        like = f"%{q}%"
        query = query.filter(
            (SalesDoc.doc_no.ilike(like))
            | (SalesDoc.customer_name.ilike(like))
            | (SalesDoc.subject.ilike(like))
            | (SalesDoc.description.ilike(like))
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
        DOC_STATUS_BY_TYPE=DOC_STATUS_BY_TYPE,
    )


@bp_docs.get("/docs/qt/new")
def qt_new():
    return render_template(
        "docs/form_qt.html",
        doc=None,
        doc_no=SalesDoc.next_doc_no("QT"),
        today=_today(),
        items=[{"description": "", "qty": "1", "unit_price": "0", "discount_amount": "0"}],
        installments=[
            {
                "title": "งวดที่ 1",
                "percent": "100",
                "due_date": "",
                "remark": "",
            }
        ],
    )


@bp_docs.post("/docs/qt/new")
def qt_create():
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
        status=_doc_status("QT", "draft"),
        issue_date=_today(),
        due_date=_parse_any_date(request.form.get("due_date") or ""),
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

    if customer:
        doc.customer_id = customer.id
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

    w_end_raw = (
        request.form.get("warranty_end_date")
        or request.form.get("warranty_end_date_hidden")
        or ""
    )
    if hasattr(doc, "warranty_end_date"):
        doc.warranty_end_date = _parse_any_date(w_end_raw)

    _snapshot_company_to_doc(doc)

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
    db.session.flush()

    try:
        _upsert_installments_from_request(doc)
    except ValueError as e:
        db.session.rollback()
        flash(str(e), "error")
        return redirect(url_for("docs.qt_new"))

    db.session.commit()

    flash(f"สร้างใบเสนอราคา {doc.doc_no} เรียบร้อย", "success")
    return redirect(url_for("docs.doc_view", doc_id=doc.id))


@bp_docs.get("/docs/<int:doc_id>")
def doc_view(doc_id: int):
    doc = (
        SalesDoc.query.options(
            joinedload(SalesDoc.customer),
            joinedload(SalesDoc.installment),
            joinedload(SalesDoc.installments),
        )
        .get_or_404(doc_id)
    )

    children = []
    installments = []
    if doc.doc_type == "QT":
        children = (
            SalesDoc.query.filter_by(parent_id=doc.id)
            .order_by(SalesDoc.installment_id.asc().nullsfirst(), SalesDoc.id.asc())
            .all()
        )
        installments = (
            SalesInstallment.query.filter_by(quote_id=doc.id)
            .order_by(SalesInstallment.installment_no.asc())
            .all()
        )
        for inst in installments:
            _sync_installment_status(inst)
        db.session.commit()

    return render_template(
        "docs/view.html",
        doc=doc,
        children=children,
        installments=installments,
        DOC_TITLE=DOC_TITLE,
        DOC_STATUS_BY_TYPE=DOC_STATUS_BY_TYPE,
        INSTALLMENT_STATUS=INSTALLMENT_STATUS,
    )


@bp_docs.post("/docs/<int:doc_id>/approve")
def doc_approve(doc_id: int):
    doc = SalesDoc.query.options(joinedload(SalesDoc.customer)).get_or_404(doc_id)

    if _is_doc_status(doc, "approved"):
        return redirect(url_for("docs.doc_view", doc_id=doc.id))

    doc.status = _doc_status(doc.doc_type, "approved")
    doc.approved_by = (request.form.get("approved_by") or "").strip() or "ADMIN"
    doc.approved_at = datetime.utcnow()

    if doc.doc_type == "QT":
        _ensure_project_from_qt(doc)

    if doc.installment_id:
        inst = SalesInstallment.query.get(doc.installment_id)
        if inst:
            if doc.doc_type == "BL":
                inst.billing_doc_id = doc.id
            elif doc.doc_type == "IV":
                inst.invoice_doc_id = doc.id
            elif doc.doc_type == "RC":
                inst.receipt_doc_id = doc.id
            _sync_installment_status(inst)

    db.session.commit()
    flash("อนุมัติเอกสารแล้ว", "success")
    return redirect(url_for("docs.doc_view", doc_id=doc.id))


@bp_docs.post("/docs/<int:doc_id>/installments/save")
def installments_save(doc_id: int):
    doc = SalesDoc.query.get_or_404(doc_id)

    if (doc.doc_type or "").upper() != "QT":
        flash("บันทึกงวดได้เฉพาะใบเสนอราคา (QT)", "error")
        return redirect(url_for("docs.doc_view", doc_id=doc.id))

    try:
        _upsert_installments_from_request(doc)
        db.session.commit()
        flash("บันทึกแผนงวดเรียบร้อย", "success")
    except ValueError as e:
        db.session.rollback()
        flash(str(e), "error")

    return redirect(url_for("docs.doc_view", doc_id=doc.id))


@bp_docs.post("/docs/installments/<int:installment_id>/create/<string:child_type>")
def installment_create_child(installment_id: int, child_type: str):
    child_type = (child_type or "").upper().strip()
    if child_type not in ("IV", "RC", "BL"):
        abort(404)

    inst = SalesInstallment.query.get_or_404(installment_id)
    parent = SalesDoc.query.get_or_404(inst.quote_id)

    if parent.doc_type != "QT":
        flash("สร้างเอกสารถัดไปได้เฉพาะจากใบเสนอราคา (QT) เท่านั้น", "error")
        return redirect(url_for("docs.doc_view", doc_id=parent.id))

    if not _is_doc_status(parent, "approved"):
        flash("ต้องอนุมัติใบเสนอราคา (QT) ก่อน ถึงจะสร้างเอกสารถัดไปได้", "error")
        return redirect(url_for("docs.doc_view", doc_id=parent.id))

    existing_id = None
    if child_type == "BL":
        existing_id = inst.billing_doc_id
    elif child_type == "IV":
        existing_id = inst.invoice_doc_id
    elif child_type == "RC":
        existing_id = inst.receipt_doc_id

    if existing_id:
        existing = SalesDoc.query.get(existing_id)
        if existing:
            flash(f"{DOC_TITLE.get(child_type, child_type)} ของงวดนี้ถูกสร้างไว้แล้ว", "info")
            return redirect(url_for("docs.doc_view", doc_id=existing.id))

    child = _clone_child_from_installment(parent, inst, child_type)
    db.session.add(child)
    db.session.flush()

    if child_type == "BL":
        inst.billing_doc_id = child.id
    elif child_type == "IV":
        inst.invoice_doc_id = child.id
    elif child_type == "RC":
        inst.receipt_doc_id = child.id

    _sync_installment_status(inst)

    db.session.commit()
    flash(f"สร้าง {DOC_TITLE.get(child_type, child_type)} {child.doc_no} เรียบร้อย", "success")
    return redirect(url_for("docs.doc_view", doc_id=child.id))


@bp_docs.post("/docs/<int:doc_id>/create/<string:child_type>")
def doc_create_child(doc_id: int, child_type: str):
    """
    backward compatible route เดิม
    - ถ้า QT มีหลายงวดแล้ว ให้บังคับไปออกจากงวด
    - ถ้ายังไม่มีงวดเลย จะสร้างงวด 100% ให้เอง
    """
    child_type = (child_type or "").upper().strip()
    if child_type not in ("IV", "RC", "BL"):
        abort(404)

    parent = SalesDoc.query.get_or_404(doc_id)

    if parent.doc_type != "QT":
        flash("สร้างเอกสารถัดไปได้เฉพาะจากใบเสนอราคา (QT) เท่านั้น", "error")
        return redirect(url_for("docs.doc_view", doc_id=parent.id))

    if not _is_doc_status(parent, "approved"):
        flash("ต้องอนุมัติใบเสนอราคา (QT) ก่อน ถึงจะสร้างเอกสารถัดไปได้", "error")
        return redirect(url_for("docs.doc_view", doc_id=parent.id))

    if len(parent.installments or []) > 1:
        flash("ใบเสนอราคานี้มีหลายงวด กรุณาออกเอกสารจากแถวของงวดที่ต้องการ", "warning")
        return redirect(url_for("docs.doc_view", doc_id=parent.id))

    child = _clone_child_from_parent(parent, child_type)
    db.session.add(child)
    db.session.flush()

    inst = child.installment
    if inst:
        if child_type == "BL":
            inst.billing_doc_id = child.id
        elif child_type == "IV":
            inst.invoice_doc_id = child.id
        elif child_type == "RC":
            inst.receipt_doc_id = child.id
        _sync_installment_status(inst)

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
        DOC_STATUS_BY_TYPE=DOC_STATUS_BY_TYPE,
    )


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
    download_name = _boq_download_name(rel, fallback_prefix=f"{doc.doc_no or 'boq'}.xlsx")
    return send_from_directory(
        directory,
        filename,
        as_attachment=True,
        download_name=download_name,
    )


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
    download_name = _boq_download_name(rel, fallback_prefix=f"{doc.doc_no or 'boq'}.pdf")
    return send_from_directory(
        directory,
        filename,
        as_attachment=True,
        download_name=download_name,
    )


@bp_docs.get("/docs/<int:doc_id>/edit")
def doc_edit(doc_id):
    doc = SalesDoc.query.options(
        joinedload(SalesDoc.customer),
        joinedload(SalesDoc.installments),
    ).get_or_404(doc_id)

    if not _is_doc_status(doc, "draft"):
        flash("เอกสารสถานะนี้ไม่สามารถแก้ไขได้ (อนุญาตเฉพาะฉบับร่าง)", "warning")
        return redirect(url_for("docs.doc_view", doc_id=doc.id))

    items = []
    for it in (doc.items or []):
        items.append(
            {
                "description": it.description or "",
                "qty": str(it.qty or "1"),
                "unit_price": str(it.unit_price or "0"),
                "discount_amount": str(it.discount_amount or "0"),
            }
        )

    if not items:
        items = [{"description": "", "qty": "1", "unit_price": "0", "discount_amount": "0"}]

    installments = []
    for inst in (doc.installments or []):
        installments.append(
            {
                "title": inst.title or f"งวดที่ {inst.installment_no}",
                "percent": str(inst.percent or "0"),
                "due_date": inst.due_date.isoformat() if inst.due_date else "",
                "remark": inst.remark or "",
                "status": inst.status or INSTALLMENT_STATUS["new"],
            }
        )

    if not installments and doc.doc_type == "QT":
        installments = [
            {
                "title": "งวดที่ 1",
                "percent": "100",
                "due_date": doc.due_date.isoformat() if doc.due_date else "",
                "remark": "",
                "status": INSTALLMENT_STATUS["new"],
            }
        ]

    return render_template(
        "docs/edit.html",
        doc=doc,
        items=items,
        installments=installments,
        DOC_TITLE=DOC_TITLE,
        DOC_STATUS_BY_TYPE=DOC_STATUS_BY_TYPE,
        INSTALLMENT_STATUS=INSTALLMENT_STATUS,
    )


@bp_docs.post("/docs/<int:doc_id>/edit")
def doc_edit_save(doc_id):
    doc = SalesDoc.query.options(
        joinedload(SalesDoc.customer),
        joinedload(SalesDoc.installments),
    ).get_or_404(doc_id)

    if not _is_doc_status(doc, "draft"):
        flash("เอกสารสถานะนี้ไม่สามารถแก้ไขได้", "warning")
        return redirect(url_for("docs.doc_view", doc_id=doc.id))

    f = request.form

    # -----------------------------
    # ลูกค้า
    # -----------------------------
    customer_id_raw = (f.get("customer_id") or "").strip()
    customer_name_raw = (f.get("customer_name") or "").strip()

    customer = None
    if customer_id_raw.isdigit():
        customer = Customer.query.get(int(customer_id_raw))

    if customer:
        doc.customer_id = customer.id

        if not customer_name_raw:
            customer_name_raw = customer.name

        doc.customer_tax_id = (f.get("customer_tax_id") or "").strip() or customer.tax_id
        doc.customer_address = (f.get("customer_address") or "").strip() or customer.address
        doc.customer_phone = (f.get("customer_phone") or "").strip() or customer.phone
        doc.customer_email = (f.get("customer_email") or "").strip() or customer.email
    else:
        doc.customer_id = None
        doc.customer_tax_id = (f.get("customer_tax_id") or "").strip() or None
        doc.customer_address = (f.get("customer_address") or "").strip() or None
        doc.customer_phone = (f.get("customer_phone") or "").strip() or None
        doc.customer_email = (f.get("customer_email") or "").strip() or None

    if not customer_name_raw:
        flash("กรุณากรอกชื่อลูกค้า", "error")
        return redirect(url_for("docs.doc_edit", doc_id=doc.id))

    doc.customer_name = customer_name_raw

    # -----------------------------
    # ข้อมูลเอกสาร
    # -----------------------------
    doc.subject = (f.get("subject") or f.get("title") or "").strip() or None
    doc.description = (f.get("description") or "").strip() or None
    doc.note = (f.get("note") or "").strip() or None
    doc.deposit_note = (f.get("deposit_note") or "").strip() or None
    doc.payment_terms = (f.get("payment_terms") or "").strip() or None
    doc.due_date = _parse_any_date(f.get("due_date") or "")

    doc.discount_amount = _to_decimal(f.get("discount_amount"), "0")
    doc.vat_rate = _to_decimal(f.get("vat_rate"), "7")
    doc.wht_rate = _to_decimal(f.get("wht_rate"), "0")

    # -----------------------------
    # รับประกัน
    # -----------------------------
    wm = (f.get("warranty_months") or "").strip()
    doc.warranty_months = int(wm) if wm.isdigit() else None

    w_end_raw = (
        f.get("warranty_end_date")
        or f.get("warranty_end_date_hidden")
        or f.get("warranty_end")
        or ""
    )
    if hasattr(doc, "warranty_end_date"):
        doc.warranty_end_date = _parse_any_date(w_end_raw)

    # -----------------------------
    # BOQ Upload ตอนแก้ไข
    # -----------------------------
    boq_excel = request.files.get("boq_excel")
    boq_pdf = request.files.get("boq_pdf")

    excel_path = _save_boq_file(boq_excel, "excel", {"xls", "xlsx"})
    pdf_path = _save_boq_file(boq_pdf, "pdf", {"pdf"})

    if boq_excel and boq_excel.filename and excel_path is None:
        flash("ไฟล์ BOQ (Excel) รองรับเฉพาะ .xls / .xlsx", "error")
        return redirect(url_for("docs.doc_edit", doc_id=doc.id))

    if boq_pdf and boq_pdf.filename and pdf_path is None:
        flash("ไฟล์ BOQ (PDF) รองรับเฉพาะ .pdf", "error")
        return redirect(url_for("docs.doc_edit", doc_id=doc.id))

    if excel_path:
        doc.boq_excel_path = excel_path
    if pdf_path:
        doc.boq_pdf_path = pdf_path

    # -----------------------------
    # รายการสินค้า/บริการ
    # รองรับหลายชื่อ field เพื่อกันฟอร์มเก่า/ใหม่
    # -----------------------------
    descs = (
        f.getlist("item_description")
        or f.getlist("description[]")
        or f.getlist("item_name[]")
    )
    qtys = (
        f.getlist("item_qty")
        or f.getlist("qty[]")
    )
    prices = (
        f.getlist("item_unit_price")
        or f.getlist("unit_price[]")
    )
    line_discs = (
        f.getlist("item_discount_amount")
        or f.getlist("discount_amount[]")
        or f.getlist("line_discount[]")
    )

    new_items = []
    row_count = max(len(descs), len(qtys), len(prices), len(line_discs))

    for i in range(row_count):
        desc = (descs[i] if i < len(descs) else "") or ""
        desc = desc.strip()

        qty = _to_decimal(qtys[i] if i < len(qtys) else "0", "0")
        price = _to_decimal(prices[i] if i < len(prices) else "0", "0")
        ldisc = _to_decimal(line_discs[i] if i < len(line_discs) else "0", "0")

        if not desc and qty == 0 and price == 0 and ldisc == 0:
            continue

        if not desc:
            desc = "(ไม่ระบุ)"

        if qty < 0:
            qty = Decimal("0")
        if price < 0:
            price = Decimal("0")
        if ldisc < 0:
            ldisc = Decimal("0")

        new_items.append(
            SalesItem(
                description=desc,
                qty=qty,
                unit_price=price,
                discount_amount=ldisc,
            )
        )

    if not new_items:
        flash("กรุณาใส่อย่างน้อย 1 รายการ", "error")
        return redirect(url_for("docs.doc_edit", doc_id=doc.id))

    doc.items.clear()
    for item in new_items:
        doc.items.append(item)

    try:
        if (doc.doc_type or "").upper() == "QT":
            _upsert_installments_from_request(doc)
    except ValueError as e:
        db.session.rollback()
        flash(str(e), "error")
        return redirect(url_for("docs.doc_edit", doc_id=doc.id))

    db.session.commit()
    flash("บันทึกการแก้ไขเอกสารเรียบร้อย", "success")
    return redirect(url_for("docs.doc_view", doc_id=doc.id))