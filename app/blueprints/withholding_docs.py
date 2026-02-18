from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from flask import Blueprint, flash, redirect, render_template, request, send_file, url_for

from .. import db
from ..models import CompanyProfile, WithholdingCertificate, WithholdingEntity, WithholdingPerson


bp_withholding_docs = Blueprint(
    "withholding_docs",
    __name__,
    url_prefix="/withholding/docs",
)


# -------------------------
# Helpers
# -------------------------
def _s(v: str | None) -> str:
    return (v or "").strip()


def _to_int(v: str | None) -> int | None:
    v = _s(v)
    if not v:
        return None
    try:
        return int(v)
    except Exception:
        return None


def _d(v) -> Decimal:
    try:
        if v is None:
            return Decimal("0")
        s = str(v).strip()
        if s == "":
            return Decimal("0")
        return Decimal(s)
    except Exception:
        return Decimal("0")


def _q2(v: Decimal) -> Decimal:
    try:
        return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return v


# =========================================================
# List
# =========================================================
@bp_withholding_docs.get("/")
def docs_list():
    q = _s(request.args.get("q"))

    qry = WithholdingCertificate.query.order_by(WithholdingCertificate.id.desc())
    if q:
        like = f"%{q}%"
        qry = qry.filter(
            (WithholdingCertificate.doc_no.ilike(like))
            | (WithholdingCertificate.payer_name.ilike(like))
        )

    docs = qry.limit(200).all()
    return render_template("withholding/docs_list.html", docs=docs, q=q)


# =========================================================
# Create
# =========================================================
@bp_withholding_docs.route("/new", methods=["GET", "POST"])
def docs_new():
    people = WithholdingPerson.query.filter_by(is_active=True).order_by(WithholdingPerson.full_name.asc()).all()
    entities = WithholdingEntity.query.filter_by(is_active=True).order_by(WithholdingEntity.company_name.asc()).all()

    if request.method == "POST":
        # โฟกัส ภงด 3/53 ก่อน (default 53)
        form_type = _s(request.form.get("form_type")) or "PND53"  # PND3 / PND53
        payee_kind = (_s(request.form.get("payee_kind")) or "PERSON").upper()  # PERSON / ENTITY

        payee_person_id = _to_int(request.form.get("payee_person_id"))
        payee_entity_id = _to_int(request.form.get("payee_entity_id"))

        payment_date_str = _s(request.form.get("payment_date"))
        try:
            payment_date = date.fromisoformat(payment_date_str) if payment_date_str else date.today()
        except Exception:
            payment_date = date.today()

        income_type = _s(request.form.get("income_type")) or None
        description = _s(request.form.get("description")) or None

        base_amount = _q2(_d(request.form.get("base_amount")))
        wht_rate = _q2(_d(request.form.get("wht_rate")))
        wht_amount = _q2(_d(request.form.get("wht_amount")))

        # -------------------------
        # Validation
        # -------------------------
        if form_type not in ("PND3", "PND53"):
            form_type = "PND53"

        if payee_kind not in ("PERSON", "ENTITY"):
            payee_kind = "PERSON"

        if payee_kind == "PERSON" and not payee_person_id:
            flash("กรุณาเลือกผู้ถูกหัก (บุคคลธรรมดา)", "error")
            return render_template("withholding/doc_form.html", doc=None, people=people, entities=entities)

        if payee_kind == "ENTITY" and not payee_entity_id:
            flash("กรุณาเลือกผู้ถูกหัก (นิติบุคคล)", "error")
            return render_template("withholding/doc_form.html", doc=None, people=people, entities=entities)

        if base_amount <= 0:
            flash("กรุณากรอกฐานภาษี (จำนวนเงิน) มากกว่า 0", "error")
            return render_template("withholding/doc_form.html", doc=None, people=people, entities=entities)

        if wht_rate < 0:
            wht_rate = Decimal("0")

        # ถ้าไม่ได้กรอกยอดหัก => คำนวณให้
        if wht_amount == 0 and base_amount > 0 and wht_rate > 0:
            wht_amount = _q2((base_amount * wht_rate) / Decimal("100"))

        payer = CompanyProfile.get_one()

        doc = WithholdingCertificate(
            form_type=form_type,
            doc_no=WithholdingCertificate.next_doc_no(form_type),

            payee_kind=payee_kind,
            payee_person_id=payee_person_id if payee_kind == "PERSON" else None,
            payee_entity_id=payee_entity_id if payee_kind == "ENTITY" else None,

            payer_name=payer.company_name or "บริษัทของฉัน",
            payer_tax_id=payer.tax_id,
            payer_address=payer.address,
            payer_branch_no="00000",

            payment_date=payment_date,

            # 1 ใบ = 1 รายการ (เราจะเก็บช่องนี้ไว้ชุดเดียว)
            income_type=income_type,
            description=description,
            base_amount=base_amount,
            wht_rate=wht_rate,
            wht_amount=wht_amount,

            is_active=True,
        )

        db.session.add(doc)
        db.session.commit()

        flash("บันทึกเอกสารหัก ณ ที่จ่ายแล้ว", "success")
        return redirect(url_for("withholding_docs.docs_list"))

    return render_template(
        "withholding/doc_form.html",
        doc=None,
        people=people,
        entities=entities,
    )


# =========================================================
# Edit
# =========================================================
@bp_withholding_docs.route("/<int:doc_id>/edit", methods=["GET", "POST"])
def docs_edit(doc_id: int):
    doc = WithholdingCertificate.query.get_or_404(doc_id)

    people = WithholdingPerson.query.filter_by(is_active=True).order_by(WithholdingPerson.full_name.asc()).all()
    entities = WithholdingEntity.query.filter_by(is_active=True).order_by(WithholdingEntity.company_name.asc()).all()

    if request.method == "POST":
        form_type = _s(request.form.get("form_type")) or doc.form_type
        payee_kind = (_s(request.form.get("payee_kind")) or doc.payee_kind).upper()

        if form_type not in ("PND3", "PND53"):
            form_type = doc.form_type
        if payee_kind not in ("PERSON", "ENTITY"):
            payee_kind = doc.payee_kind

        payee_person_id = _to_int(request.form.get("payee_person_id"))
        payee_entity_id = _to_int(request.form.get("payee_entity_id"))

        if payee_kind == "PERSON" and not payee_person_id:
            flash("กรุณาเลือกผู้ถูกหัก (บุคคลธรรมดา)", "error")
            return render_template("withholding/doc_form.html", doc=doc, people=people, entities=entities)

        if payee_kind == "ENTITY" and not payee_entity_id:
            flash("กรุณาเลือกผู้ถูกหัก (นิติบุคคล)", "error")
            return render_template("withholding/doc_form.html", doc=doc, people=people, entities=entities)

        payment_date_str = _s(request.form.get("payment_date"))
        if payment_date_str:
            try:
                doc.payment_date = date.fromisoformat(payment_date_str)
            except Exception:
                pass

        doc.form_type = form_type
        doc.payee_kind = payee_kind
        doc.payee_person_id = payee_person_id if payee_kind == "PERSON" else None
        doc.payee_entity_id = payee_entity_id if payee_kind == "ENTITY" else None

        doc.income_type = _s(request.form.get("income_type")) or None
        doc.description = _s(request.form.get("description")) or None

        doc.base_amount = _q2(_d(request.form.get("base_amount")))
        doc.wht_rate = _q2(_d(request.form.get("wht_rate")))
        doc.wht_amount = _q2(_d(request.form.get("wht_amount")))

        if doc.base_amount <= 0:
            flash("กรุณากรอกฐานภาษี (จำนวนเงิน) มากกว่า 0", "error")
            return render_template("withholding/doc_form.html", doc=doc, people=people, entities=entities)

        if doc.wht_amount == 0 and doc.base_amount > 0 and doc.wht_rate > 0:
            doc.wht_amount = _q2((doc.base_amount * doc.wht_rate) / Decimal("100"))

        doc.note = _s(request.form.get("note")) or None
        doc.is_active = True if request.form.get("is_active") in ("1", "on", "true", "True") else False

        db.session.commit()
        flash("อัพเดทเอกสารแล้ว", "success")
        return redirect(url_for("withholding_docs.docs_list"))

    return render_template(
        "withholding/doc_form.html",
        doc=doc,
        people=people,
        entities=entities,
    )


# =========================================================
# PDF
# =========================================================
@bp_withholding_docs.get("/<int:doc_id>/pdf")
def docs_pdf(doc_id: int):
    doc = WithholdingCertificate.query.get_or_404(doc_id)

    # ✅ lazy import: กัน migrate/upgrade พังถ้า reportlab ยังไม่พร้อม
    from ..utils.withholding_pdf import build_withholding_pdf

    pdf_path = build_withholding_pdf(doc)  # returns a temp file path
    return send_file(
        pdf_path,
        as_attachment=True,
        download_name=f"{doc.doc_no}.pdf",
        mimetype="application/pdf",
    )
