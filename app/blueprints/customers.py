from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from .. import db
from ..models import Customer

bp_customers = Blueprint("customers", __name__)


@bp_customers.get("/customers")
def customers_list():
    q = (request.args.get("q") or "").strip()
    query = Customer.query
    if q:
        query = query.filter(Customer.name.ilike(f"%{q}%"))
    customers = query.order_by(Customer.name.asc()).all()
    return render_template("customers/list.html", customers=customers, q=q)


@bp_customers.route("/customers/new", methods=["GET", "POST"])
def customers_new():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("กรุณากรอกชื่อลูกค้า", "error")
            return redirect(url_for("customers.customers_new"))

        c = Customer(
            name=name,
            tax_id=(request.form.get("tax_id") or "").strip() or None,
            address=(request.form.get("address") or "").strip() or None,
            phone=(request.form.get("phone") or "").strip() or None,
            email=(request.form.get("email") or "").strip() or None,
            contact_name=(request.form.get("contact_name") or "").strip() or None,
            note=(request.form.get("note") or "").strip() or None,
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

        c.name = name
        c.tax_id = (request.form.get("tax_id") or "").strip() or None
        c.address = (request.form.get("address") or "").strip() or None
        c.phone = (request.form.get("phone") or "").strip() or None
        c.email = (request.form.get("email") or "").strip() or None
        c.contact_name = (request.form.get("contact_name") or "").strip() or None
        c.note = (request.form.get("note") or "").strip() or None
        c.is_active = (request.form.get("is_active") == "1")

        db.session.commit()
        flash("แก้ไขข้อมูลลูกค้าแล้ว", "success")
        return redirect(url_for("customers.customers_list"))

    return render_template("customers/form.html", customer=c)


@bp_customers.post("/customers/<int:customer_id>/delete")
def customers_delete(customer_id: int):
    c = Customer.query.get_or_404(customer_id)
    # ปลอดภัย: ปิดการใช้งานแทนลบจริง
    c.is_active = False
    db.session.commit()
    flash("ปิดการใช้งานลูกค้าแล้ว", "success")
    return redirect(url_for("customers.customers_list"))
