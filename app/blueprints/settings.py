from __future__ import annotations

import os
from werkzeug.utils import secure_filename
from flask import Blueprint, flash, redirect, render_template, request, url_for, current_app

from .. import db
from ..models import CompanyProfile

bp_settings = Blueprint("settings", __name__)

ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def _ensure_upload_dir() -> str:
    # เก็บไว้ใน app/static/uploads
    static_dir = current_app.static_folder
    upload_dir = os.path.join(static_dir, "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir


def _allowed(filename: str) -> bool:
    ext = os.path.splitext(filename.lower())[1]
    return ext in ALLOWED_EXT


@bp_settings.get("/settings/company")
def company_settings():
    profile = CompanyProfile.get_one()
    return render_template("settings/company.html", profile=profile)


@bp_settings.post("/settings/company")
def company_settings_save():
    profile = CompanyProfile.get_one()

    profile.company_name = request.form.get("company_name", "").strip() or profile.company_name
    profile.tax_id = request.form.get("tax_id", "").strip() or None
    profile.address = request.form.get("address", "").strip() or None
    profile.phone = request.form.get("phone", "").strip() or None
    profile.email = request.form.get("email", "").strip() or None
    profile.website = request.form.get("website", "").strip() or None

    # ข้อมูลการชำระเงิน (ใช้ตอนพิมพ์ใบเสนอราคา)
    profile.payment_bank = request.form.get("payment_bank", "").strip() or None
    profile.payment_account_no = request.form.get("payment_account_no", "").strip() or None
    profile.payment_account_name = request.form.get("payment_account_name", "").strip() or None
    profile.payment_branch = request.form.get("payment_branch", "").strip() or None

    # อัปโหลดโลโก้
    f = request.files.get("logo")
    if f and f.filename:
        if not _allowed(f.filename):
            flash("ไฟล์โลโก้ต้องเป็น png/jpg/jpeg/webp เท่านั้น", "error")
            return redirect(url_for("settings.company_settings"))

        upload_dir = _ensure_upload_dir()
        safe = secure_filename(f.filename)
        # ตั้งชื่อไฟล์ให้คงที่ จะได้ไม่ซ้ำ
        ext = os.path.splitext(safe)[1].lower()
        filename = f"company_logo{ext}"
        save_path = os.path.join(upload_dir, filename)
        f.save(save_path)

        profile.logo_path = f"uploads/{filename}"

    db.session.commit()
    flash("บันทึกข้อมูลบริษัทเรียบร้อย", "success")
    return redirect(url_for("settings.company_settings"))
