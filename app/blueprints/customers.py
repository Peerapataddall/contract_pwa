from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from .. import db
from ..models import Customer

bp_customers = Blueprint("customers", __name__)


def _clean_text(v: str | None) -> str | None:
    s = (v or "").strip()
    return s or None


def _normalize_name(v: str | None) -> str:
    return " ".join((v or "").strip().lower().split())


@bp_customers.get("/customers")
def customers_list():
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "active").strip().lower()

    query = Customer.query

    if status == "inactive":
        query = query.filter(Customer.is_active.is_(False))
    elif status == "all":
        pass
    else:
        status = "active"
        query = query.filter(Customer.is_active.is_(True))

    if q:
        like = f"%{q}%"
        query = query.filter(
            (Customer.name.ilike(like))
            | (Customer.tax_id.ilike(like))
            | (Customer.phone.ilike(like))
            | (Customer.email.ilike(like))
            | (Customer.contact_name.ilike(like))
        )

    customers = query.order_by(Customer.name.asc(), Customer.id.desc()).all()

    active_count = Customer.query.filter(Customer.is_active.is_(True)).count()
    inactive_count = Customer.query.filter(Customer.is_active.is_(False)).count()
    total_count = active_count + inactive_count

    return render_template(
        "customers/list.html",
        customers=customers,
        q=q,
        status=status,
        active_count=active_count,
        inactive_count=inactive_count,
        total_count=total_count,
    )


@bp_customers.route("/customers/new", methods=["GET", "POST"])
def customers_new():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("กรุณากรอกชื่อลูกค้า", "error")
            return redirect(url_for("customers.customers_new"))

        tax_id = _clean_text(request.form.get("tax_id"))
        address = _clean_text(request.form.get("address"))
        phone = _clean_text(request.form.get("phone"))
        email = _clean_text(request.form.get("email"))
        contact_name = _clean_text(request.form.get("contact_name"))
        note = _clean_text(request.form.get("note"))

        normalized_name = _normalize_name(name)

        existing_active = Customer.query.filter(Customer.is_active.is_(True)).all()
        for row in existing_active:
            if _normalize_name(row.name) == normalized_name:
                flash(f"มีลูกค้าชื่อนี้อยู่แล้ว: {row.name}", "error")
                return redirect(url_for("customers.customers_new"))

        if tax_id:
            same_tax_active = (
                Customer.query.filter(Customer.is_active.is_(True), Customer.tax_id == tax_id).first()
            )
            if same_tax_active:
                flash(
                    f"เลขผู้เสียภาษีนี้ถูกใช้งานอยู่แล้วโดยลูกค้า: {same_tax_active.name}",
                    "error",
                )
                return redirect(url_for("customers.customers_new"))

        existing_inactive = Customer.query.filter(Customer.is_active.is_(False)).all()
        for row in existing_inactive:
            same_name = _normalize_name(row.name) == normalized_name
            same_tax = bool(tax_id and row.tax_id and row.tax_id == tax_id)
            if same_name or same_tax:
                flash(
                    f"พบลูกค้าที่เคยปิดการใช้งานไว้แล้ว: {row.name} "
                    f"กรุณาเข้าไปแก้ไขแล้วเปิดใช้งานใหม่แทนการสร้างซ้ำ",
                    "warning",
                )
                return redirect(url_for("customers.customers_edit", customer_id=row.id))

        c = Customer(
            name=name,
            tax_id=tax_id,
            address=address,
            phone=phone,
            email=email,
            contact_name=contact_name,
            note=note,
            is_active=True,
        )
        db.session.add(c)
        db.session.commit()

        flash("บันทึกลูกค้าแล้ว", "success")
        return redirect(url_for("customers.customers_list"))

    return render_template("customers/form.html", customer=None)


@bp_customers.route("/customers/<int:customer_id>/edit", methods=["GET", "POST"])
def customers_edit(customer_id: int):
    c = Customer.query.get_or_404(customer_id)

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("กรุณากรอกชื่อลูกค้า", "error")
            return redirect(url_for("customers.customers_edit", customer_id=c.id))

        tax_id = _clean_text(request.form.get("tax_id"))
        address = _clean_text(request.form.get("address"))
        phone = _clean_text(request.form.get("phone"))
        email = _clean_text(request.form.get("email"))
        contact_name = _clean_text(request.form.get("contact_name"))
        note = _clean_text(request.form.get("note"))
        is_active = (request.form.get("is_active") == "1")

        normalized_name = _normalize_name(name)

        others = Customer.query.filter(Customer.id != c.id).all()
        for row in others:
            if _normalize_name(row.name) == normalized_name and bool(row.is_active) and is_active:
                flash(f"มีลูกค้าชื่อนี้ที่กำลังใช้งานอยู่แล้ว: {row.name}", "error")
                return redirect(url_for("customers.customers_edit", customer_id=c.id))

        if tax_id and is_active:
            same_tax = (
                Customer.query.filter(
                    Customer.id != c.id,
                    Customer.is_active.is_(True),
                    Customer.tax_id == tax_id,
                ).first()
            )
            if same_tax:
                flash(
                    f"เลขผู้เสียภาษีนี้ถูกใช้งานอยู่แล้วโดยลูกค้า: {same_tax.name}",
                    "error",
                )
                return redirect(url_for("customers.customers_edit", customer_id=c.id))

        c.name = name
        c.tax_id = tax_id
        c.address = address
        c.phone = phone
        c.email = email
        c.contact_name = contact_name
        c.note = note
        c.is_active = is_active

        db.session.commit()
        flash("แก้ไขข้อมูลลูกค้าแล้ว", "success")
        return redirect(url_for("customers.customers_list", status="active" if c.is_active else "inactive"))

    return render_template("customers/form.html", customer=c)


@bp_customers.post("/customers/<int:customer_id>/delete")
def customers_delete(customer_id: int):
    c = Customer.query.get_or_404(customer_id)

    if not c.is_active:
        flash("ลูกค้ารายการนี้ถูกปิดการใช้งานไว้แล้ว", "info")
        return redirect(url_for("customers.customers_list", status="inactive"))

    c.is_active = False
    db.session.commit()

    flash("ปิดการใช้งานลูกค้าแล้ว", "success")
    return redirect(url_for("customers.customers_list", status="active"))


@bp_customers.post("/customers/<int:customer_id>/restore")
def customers_restore(customer_id: int):
    c = Customer.query.get_or_404(customer_id)

    normalized_name = _normalize_name(c.name)

    active_rows = Customer.query.filter(Customer.id != c.id, Customer.is_active.is_(True)).all()
    for row in active_rows:
        if _normalize_name(row.name) == normalized_name:
            flash(
                f"ไม่สามารถเปิดใช้งานลูกค้ารายนี้ได้ เพราะมีลูกค้าชื่อเดียวกันที่กำลังใช้งานอยู่: {row.name}",
                "error",
            )
            return redirect(url_for("customers.customers_list", status="inactive"))

    if c.tax_id:
        same_tax = (
            Customer.query.filter(
                Customer.id != c.id,
                Customer.is_active.is_(True),
                Customer.tax_id == c.tax_id,
            ).first()
        )
        if same_tax:
            flash(
                f"ไม่สามารถเปิดใช้งานลูกค้ารายนี้ได้ เพราะเลขผู้เสียภาษีซ้ำกับลูกค้าที่กำลังใช้งานอยู่: {same_tax.name}",
                "error",
            )
            return redirect(url_for("customers.customers_list", status="inactive"))

    c.is_active = True
    db.session.commit()

    flash("เปิดใช้งานลูกค้าแล้ว", "success")
    return redirect(url_for("customers.customers_list", status="active"))