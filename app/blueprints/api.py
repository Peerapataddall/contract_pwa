from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError

from .. import db
from ..models import (
    AdvanceExpense,
    Customer,
    MaterialItem,
    OtherExpense,
    Project,
    SubcontractorPayment,
)

bp_api = Blueprint("api", __name__)

ALLOWED_PROJECT_STATUS = {"IN_PROGRESS", "DEFECT", "DONE"}


def _parse_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _to_float(x):
    if x is None:
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    try:
        s = str(x).strip()
        if s == "":
            return 0.0
        s = s.replace(",", "")
        return float(s)
    except Exception:
        return 0.0


def _clean_text(v):
    s = str(v or "").strip()
    return s or None


def _nonneg_float(x, field_label: str) -> float:
    v = _to_float(x)
    if v < 0:
        raise ValueError(f"{field_label} ต้องไม่ติดลบ")
    return v


def _nonneg_int(x, field_label: str) -> int:
    try:
        v = int(str(x or "0").strip() or "0")
    except Exception:
        v = 0
    if v < 0:
        raise ValueError(f"{field_label} ต้องไม่ติดลบ")
    return v


@bp_api.get("/projects/<int:pid>")
def get_project(pid: int):
    p = Project.query.get_or_404(pid)
    return jsonify(_serialize_project(p))


@bp_api.post("/projects")
def create_project():
    payload = request.get_json(silent=True) or {}
    p = Project()

    try:
        _apply_project_payload(p, payload)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    db.session.add(p)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"ok": False, "error": "รหัสโครงการซ้ำ กรุณาใช้รหัสใหม่"}), 400

    return jsonify({"ok": True, "id": p.id})


@bp_api.put("/projects/<int:pid>")
def update_project(pid: int):
    p = Project.query.get_or_404(pid)
    payload = request.get_json(silent=True) or {}

    try:
        _apply_project_payload(p, payload)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"ok": False, "error": "รหัสโครงการซ้ำ กรุณาใช้รหัสใหม่"}), 400

    return jsonify({"ok": True, "id": p.id})


@bp_api.delete("/projects/<int:pid>")
def delete_project(pid: int):
    p = Project.query.get_or_404(pid)
    db.session.delete(p)
    db.session.commit()
    return jsonify({"ok": True})


def _serialize_project(p: Project) -> dict:
    return {
        "id": p.id,
        "code": p.code,
        "name": p.name,
        "description": p.description,
        "customer_name": p.customer_name,
        "location": p.location,
        "start_date": p.start_date.isoformat() if p.start_date else "",
        "end_date": p.end_date.isoformat() if p.end_date else "",
        "work_days": p.work_days,
        "status": p.status,
        "totals": {
            "materials": p.total_material_cost,
            "subcontractors": p.total_subcontractor_cost,
            "other": p.total_other_expense,
            "advances": p.total_advance_expense,
            "grand": p.total_cost,
        },
        "materials": [
            {
                "id": m.id,
                "brand": m.brand or "",
                "item_code": m.item_code or "",
                "item_name": m.item_name or "",
                "unit": m.unit or "",
                "tax_invoice_no": (getattr(m, "tax_invoice_no", None) or ""),
                "tax_invoice_date": (
                    getattr(m, "tax_invoice_date").isoformat()
                    if getattr(m, "tax_invoice_date", None)
                    else ""
                ),
                "unit_price": float(m.unit_price or 0),
                "qty": float(m.qty or 0),
                "note": m.note or "",
            }
            for m in (p.materials or [])
        ],
        "subcontractors": [
            {
                "id": s.id,
                "vendor_name": s.vendor_name,
                "pay_date": s.pay_date.isoformat() if getattr(s, "pay_date", None) else "",
                "contract_amount": float(s.contract_amount or 0),
                "withholding_rate": float(s.withholding_rate or 0),
                "withholding_amount": float(s.withholding_amount or 0),
                "note": s.note or "",
            }
            for s in (p.subcontractors or [])
        ],
        "expenses": [
            {
                "id": e.id,
                "category": e.category or "",
                "title": e.title,
                "expense_date": e.expense_date.isoformat() if getattr(e, "expense_date", None) else "",
                "amount": float(e.amount or 0),
                "note": e.note or "",
            }
            for e in (p.expenses or [])
        ],
        "advances": [
            {
                "id": a.id,
                "title": a.title,
                "advance_date": a.advance_date.isoformat() if getattr(a, "advance_date", None) else "",
                "amount": float(a.amount or 0),
                "note": a.note or "",
            }
            for a in (p.advances or [])
        ],
    }


def _apply_project_payload(p: Project, payload: dict) -> None:
    code = (payload.get("code") or "").strip()
    name = (payload.get("name") or "").strip()
    description = _clean_text(payload.get("description"))
    customer_name = _clean_text(payload.get("customer_name"))
    location = _clean_text(payload.get("location"))
    start_date = _parse_date(payload.get("start_date"))
    end_date = _parse_date(payload.get("end_date"))
    work_days = _nonneg_int(payload.get("work_days"), "จำนวนวันทำงาน")
    status = (payload.get("status") or "IN_PROGRESS").strip().upper()

    if not code:
        raise ValueError("กรุณากรอกรหัสโครงการ")
    if not name:
        raise ValueError("กรุณากรอกชื่อโครงการ")
    if status not in ALLOWED_PROJECT_STATUS:
        raise ValueError("สถานะโครงการไม่ถูกต้อง")
    if start_date and end_date and end_date < start_date:
        raise ValueError("วันที่สิ้นสุดต้องไม่น้อยกว่าวันเริ่มต้น")

    p.code = code
    p.name = name
    p.description = description
    p.customer_name = customer_name
    p.location = location
    p.start_date = start_date
    p.end_date = end_date
    p.work_days = work_days
    p.status = status

    # clear and recreate children
    p.materials.clear()
    p.subcontractors.clear()
    p.expenses.clear()
    p.advances.clear()

    for idx, row in enumerate(payload.get("materials") or [], start=1):
        brand = _clean_text(row.get("brand"))
        item_code = _clean_text(row.get("item_code"))
        item_name = _clean_text(row.get("item_name"))
        unit = _clean_text(row.get("unit"))
        tax_invoice_no = _clean_text(row.get("tax_invoice_no"))
        tax_invoice_date = _parse_date(row.get("tax_invoice_date"))
        unit_price = _nonneg_float(row.get("unit_price"), f"ราคาต่อหน่วยวัสดุ แถวที่ {idx}")
        qty = _nonneg_float(row.get("qty"), f"จำนวนวัสดุ แถวที่ {idx}")
        note = _clean_text(row.get("note"))

        has_any_text = bool(brand or item_code or item_name or unit or tax_invoice_no or note)
        has_any_amount = (unit_price != 0) or (qty != 0)

        if (not has_any_text) and (not has_any_amount) and (not tax_invoice_date):
            continue

        if qty > 0 and not item_name:
            raise ValueError(f"กรุณากรอกชื่อวัสดุ แถวที่ {idx}")
        if unit_price > 0 and not item_name:
            raise ValueError(f"กรุณากรอกชื่อวัสดุ แถวที่ {idx}")

        m = MaterialItem(
            brand=brand,
            item_code=item_code,
            item_name=item_name or "(ไม่ระบุ)",
            unit=unit,
            tax_invoice_no=tax_invoice_no,
            tax_invoice_date=tax_invoice_date,
            unit_price=unit_price,
            qty=qty,
            note=note,
        )
        p.materials.append(m)

    for idx, row in enumerate(payload.get("subcontractors") or [], start=1):
        vendor_name = (row.get("vendor_name") or "").strip()
        pay_date = _parse_date(row.get("pay_date"))
        contract_amount = _nonneg_float(row.get("contract_amount"), f"ยอดผู้รับเหมาช่วง แถวที่ {idx}")
        wht_rate = _nonneg_float(row.get("withholding_rate"), f"อัตราหัก ณ ที่จ่ายผู้รับเหมาช่วง แถวที่ {idx}")
        wht_amount = _to_float(row.get("withholding_amount"))
        note = _clean_text(row.get("note"))

        if not vendor_name and contract_amount == 0 and wht_rate == 0 and wht_amount == 0 and not pay_date and not note:
            continue

        if wht_amount < 0:
            raise ValueError(f"ยอดหัก ณ ที่จ่ายผู้รับเหมาช่วง แถวที่ {idx} ต้องไม่ติดลบ")
        if wht_rate > 100:
            raise ValueError(f"อัตราหัก ณ ที่จ่ายผู้รับเหมาช่วง แถวที่ {idx} ต้องไม่เกิน 100%")

        if wht_amount == 0 and wht_rate > 0:
            wht_amount = round(contract_amount * wht_rate / 100.0, 2)

        if wht_amount > contract_amount:
            raise ValueError(f"ยอดหัก ณ ที่จ่ายผู้รับเหมาช่วง แถวที่ {idx} มากกว่ายอดจ้างไม่ได้")

        s = SubcontractorPayment(
            vendor_name=vendor_name or "(ไม่ระบุชื่อ)",
            pay_date=pay_date,
            contract_amount=contract_amount,
            withholding_rate=wht_rate,
            withholding_amount=wht_amount,
            note=note,
        )
        p.subcontractors.append(s)

    for idx, row in enumerate(payload.get("expenses") or [], start=1):
        category = (row.get("category") or "อื่นๆ").strip() or "อื่นๆ"
        title = (row.get("title") or "").strip()
        expense_date = _parse_date(row.get("expense_date"))
        amount = _nonneg_float(row.get("amount"), f"ค่าใช้จ่ายอื่น แถวที่ {idx}")
        note = _clean_text(row.get("note"))

        if not title and amount == 0 and not expense_date and not note and category == "อื่นๆ":
            continue

        e = OtherExpense(
            category=category,
            title=title or "(ไม่ระบุ)",
            expense_date=expense_date,
            amount=amount,
            note=note,
        )
        p.expenses.append(e)

    for idx, row in enumerate(payload.get("advances") or [], start=1):
        title = (row.get("title") or "").strip()
        advance_date = _parse_date(row.get("advance_date"))
        amount = _nonneg_float(row.get("amount"), f"เงินเบิกล่วงหน้า แถวที่ {idx}")
        note = _clean_text(row.get("note"))

        if not title and amount == 0 and not advance_date and not note:
            continue

        a = AdvanceExpense(
            title=title or "(ไม่ระบุ)",
            advance_date=advance_date,
            amount=amount,
            note=note,
        )
        p.advances.append(a)


# -------------------------
# Customers API (autocomplete)
# -------------------------
@bp_api.get("/customers/search")
def customers_search():
    q = (request.args.get("q") or "").strip()
    limit = min(int(request.args.get("limit") or 10), 50)

    if not q:
        return jsonify([])

    items = (
        Customer.query
        .filter(Customer.is_active.is_(True))
        .filter(
            (Customer.name.ilike(f"%{q}%"))
            | (Customer.tax_id.ilike(f"%{q}%"))
            | (Customer.phone.ilike(f"%{q}%"))
            | (Customer.email.ilike(f"%{q}%"))
        )
        .order_by(Customer.name.asc())
        .limit(limit)
        .all()
    )

    return jsonify([
        {
            "id": c.id,
            "name": c.name,
            "tax_id": c.tax_id,
            "phone": c.phone,
            "email": c.email,
            "address": c.address,
        }
        for c in items
    ])


@bp_api.get("/customers/<int:customer_id>")
def customer_get(customer_id: int):
    c = Customer.query.get_or_404(customer_id)
    return jsonify(
        {
            "id": c.id,
            "name": c.name,
            "tax_id": c.tax_id,
            "phone": c.phone,
            "email": c.email,
            "address": c.address,
            "contact_name": c.contact_name,
            "note": c.note,
            "is_active": c.is_active,
        }
    )