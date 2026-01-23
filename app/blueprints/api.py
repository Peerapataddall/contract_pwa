from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError

from .. import db
from ..models import MaterialItem, OtherExpense, Project, SubcontractorPayment

bp_api = Blueprint("api", __name__)


def _parse_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _to_float(x):
    try:
        return float(x)
    except Exception:
        return 0.0


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
        return jsonify({"ok": False, "error": "รหัสโครงการซ้ำ (code ต้องไม่ซ้ำ)"}), 400

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
        return jsonify({"ok": False, "error": "รหัสโครงการซ้ำ (code ต้องไม่ซ้ำ)"}), 400

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
            "grand": p.total_cost,
        },
        "materials": [
            {
                "id": m.id,
                "brand": m.brand or "",
                "item_code": m.item_code or "",
                "item_name": m.item_name or "",
                "unit": m.unit or "",
                "unit_price": float(m.unit_price or 0),
                "qty": float(m.qty or 0),
                "note": m.note or "",
            }
            for m in p.materials
        ],
        "subcontractors": [
            {
                "id": s.id,
                "vendor_name": s.vendor_name,
                "contract_amount": float(s.contract_amount or 0),
                "withholding_rate": float(s.withholding_rate or 0),
                "withholding_amount": float(s.withholding_amount or 0),
                "note": s.note or "",
            }
            for s in p.subcontractors
        ],
        "expenses": [
            {
                "id": e.id,
                "category": e.category or "",
                "title": e.title,
                "amount": float(e.amount or 0),
                "note": e.note or "",
            }
            for e in p.expenses
        ],
    }


def _apply_project_payload(p: Project, payload: dict) -> None:
    p.code = (payload.get("code") or "").strip()
    p.name = (payload.get("name") or "").strip()
    p.description = (payload.get("description") or "").strip() or None
    p.customer_name = (payload.get("customer_name") or "").strip() or None
    p.location = (payload.get("location") or "").strip() or None
    p.start_date = _parse_date(payload.get("start_date"))
    p.end_date = _parse_date(payload.get("end_date"))
    p.work_days = int(payload.get("work_days") or 0)
    p.status = (payload.get("status") or "IN_PROGRESS").strip().upper()

    # clear and recreate children (ง่ายต่อ UI หน้าเดียว)
    p.materials.clear()
    p.subcontractors.clear()
    p.expenses.clear()

    for row in payload.get("materials") or []:
        m = MaterialItem(
            brand=(row.get("brand") or "").strip() or None,
            item_code=(row.get("item_code") or "").strip() or None,
            item_name=(row.get("item_name") or "").strip() or None,
            unit=(row.get("unit") or "").strip() or None,
            unit_price=_to_float(row.get("unit_price")),
            qty=_to_float(row.get("qty")),
            note=(row.get("note") or "").strip() or None,
        )
        # ข้ามบรรทัดว่างทั้งหมด
        if not (m.brand or m.item_code or m.item_name) and (m.unit_price == 0 and m.qty == 0):
            continue
        p.materials.append(m)

    for row in payload.get("subcontractors") or []:
        vendor_name = (row.get("vendor_name") or "").strip()
        if not vendor_name and _to_float(row.get("contract_amount")) == 0:
            continue

        contract_amount = _to_float(row.get("contract_amount"))
        wht_rate = _to_float(row.get("withholding_rate"))
        wht_amount = _to_float(row.get("withholding_amount"))

        # ถ้าไม่กรอก withholding_amount แต่กรอก rate ให้คำนวณอัตโนมัติ
        if wht_amount == 0 and wht_rate > 0:
            wht_amount = round(contract_amount * wht_rate / 100.0, 2)

        s = SubcontractorPayment(
            vendor_name=vendor_name or "(ไม่ระบุชื่อ)",
            contract_amount=contract_amount,
            withholding_rate=wht_rate,
            withholding_amount=wht_amount,
            note=(row.get("note") or "").strip() or None,
        )
        p.subcontractors.append(s)

    for row in payload.get("expenses") or []:
        title = (row.get("title") or "").strip()
        amount = _to_float(row.get("amount"))
        if not title and amount == 0:
            continue

        e = OtherExpense(
            category=(row.get("category") or "อื่นๆ").strip() or "อื่นๆ",
            title=title or "(ไม่ระบุ)",
            amount=amount,
            note=(row.get("note") or "").strip() or None,
        )
        p.expenses.append(e)

    # validation เบื้องต้น
    if not p.code:
        raise ValueError("code is required")
    if not p.name:
        raise ValueError("name is required")
