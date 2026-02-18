from __future__ import annotations

from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy.orm import joinedload

from .. import db
from ..models import WithholdingPerson, WithholdingEntity, Customer

bp_withholding = Blueprint(
    "withholding",
    __name__,
    url_prefix="/withholding",
)

# =========================================================
# Helpers
# =========================================================

def _s(v: str | None) -> str:
    """Safe strip."""
    return (v or "").strip()


def _to_int(v: str | None) -> int | None:
    """Convert to int or None."""
    v = _s(v)
    if not v:
        return None
    try:
        return int(v)
    except Exception:
        return None


# =========================================================
# บุคคลธรรมดา (ลูกจ้าง/ผู้รับเหมาช่วง)
# =========================================================

@bp_withholding.route("/people")
def people_list():
    q = _s(request.args.get("q"))

    query = WithholdingPerson.query

    if q:
        like = f"%{q}%"
        query = query.filter(
            (WithholdingPerson.full_name.ilike(like)) |
            (WithholdingPerson.tax_id.ilike(like))
        )

    rows = query.order_by(WithholdingPerson.full_name.asc()).all()

    return render_template(
        "withholding/people_list.html",
        rows=rows,
        q=q,
    )


@bp_withholding.route("/people/new", methods=["GET", "POST"])
@bp_withholding.route("/people/<int:pid>/edit", methods=["GET", "POST"])
def people_form(pid: int | None = None):
    person = WithholdingPerson.query.get_or_404(pid) if pid else None

    if request.method == "POST":
        full_name = _s(request.form.get("full_name"))
        person_type = _s(request.form.get("person_type") or "EMPLOYEE").upper()
        tax_id = _s(request.form.get("tax_id"))
        address = _s(request.form.get("address"))
        phone = _s(request.form.get("phone"))
        note = _s(request.form.get("note"))
        is_active = True if request.form.get("is_active") in ("1", "on", "true", "True") else False

        # basic validation
        if not full_name:
            flash("กรุณากรอกชื่อ-นามสกุล", "error")
            return render_template("withholding/people_form.html", person=person)

        if person_type not in ("EMPLOYEE", "SUBCONTRACTOR"):
            person_type = "EMPLOYEE"

        if not person:
            person = WithholdingPerson()
            db.session.add(person)

        person.full_name = full_name
        person.person_type = person_type
        person.tax_id = tax_id
        person.address = address
        person.phone = phone
        person.note = note
        person.is_active = is_active

        db.session.commit()
        flash("บันทึกข้อมูลเรียบร้อย", "success")
        return redirect(url_for("withholding.people_list"))

    return render_template(
        "withholding/people_form.html",
        person=person,
    )


# =========================================================
# นิติบุคคล (บริษัท/ห้าง/องค์กร)
# =========================================================

@bp_withholding.route("/entities")
def entities_list():
    q = _s(request.args.get("q"))

    query = WithholdingEntity.query.options(
        joinedload(WithholdingEntity.customer)
    )

    if q:
        like = f"%{q}%"
        query = query.filter(
            (WithholdingEntity.company_name.ilike(like)) |
            (WithholdingEntity.tax_id.ilike(like))
        )

    rows = query.order_by(WithholdingEntity.company_name.asc()).all()

    return render_template(
        "withholding/entities_list.html",
        rows=rows,
        q=q,
    )


@bp_withholding.route("/entities/new", methods=["GET", "POST"])
@bp_withholding.route("/entities/<int:eid>/edit", methods=["GET", "POST"])
def entities_form(eid: int | None = None):
    entity = (
        WithholdingEntity.query.options(joinedload(WithholdingEntity.customer)).get_or_404(eid)
        if eid
        else None
    )

    customers = Customer.query.order_by(Customer.name.asc()).all()

    if request.method == "POST":
        company_name = _s(request.form.get("company_name"))
        tax_id = _s(request.form.get("tax_id"))
        address = _s(request.form.get("address"))
        phone = _s(request.form.get("phone"))
        email = _s(request.form.get("email"))
        contact_name = _s(request.form.get("contact_name"))
        note = _s(request.form.get("note"))
        is_active = True if request.form.get("is_active") in ("1", "on", "true", "True") else False

        customer_id = _to_int(request.form.get("customer_id"))

        # basic validation
        if not company_name:
            flash("กรุณากรอกชื่อบริษัท/นิติบุคคล", "error")
            return render_template(
                "withholding/entities_form.html",
                entity=entity,
                customers=customers,
            )

        if not entity:
            entity = WithholdingEntity()
            db.session.add(entity)

        entity.company_name = company_name
        entity.tax_id = tax_id
        entity.address = address
        entity.phone = phone
        # รองรับกรณี model มี field เหล่านี้ / ไม่มี ก็ไม่พัง
        if hasattr(entity, "email"):
            entity.email = email
        if hasattr(entity, "contact_name"):
            entity.contact_name = contact_name

        entity.note = note
        entity.customer_id = customer_id
        entity.is_active = is_active

        db.session.commit()
        flash("บันทึกข้อมูลเรียบร้อย", "success")
        return redirect(url_for("withholding.entities_list"))

    return render_template(
        "withholding/entities_form.html",
        entity=entity,
        customers=customers,
    )
