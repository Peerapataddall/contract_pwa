from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta
from io import BytesIO

from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    url_for,
)
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import joinedload

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from .. import db
from ..models import (
    AdvanceExpense,
    MaterialItem,
    OtherExpense,
    Project,
    SalesDoc,
    SubcontractorPayment,
)

bp_pages = Blueprint("pages", __name__)


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def _num(x):
    try:
        return float(x or 0)
    except Exception:
        return 0.0


def _pick_month_date(obj, *attr_names):
    for a in attr_names:
        try:
            dt = getattr(obj, a, None)
            if dt:
                return dt
        except Exception:
            pass
    try:
        return getattr(obj, "created_at", None)
    except Exception:
        return None


def _project_totals(p: Project):
    materials = sum(_num(m.unit_price) * _num(m.qty) for m in (p.materials or []))
    subs_pay = sum(
        (_num(s.contract_amount) - _num(s.withholding_amount))
        for s in (p.subcontractors or [])
    )
    expenses = sum(_num(e.amount) for e in (p.expenses or []))
    advances = sum(_num(a.amount) for a in (getattr(p, "advances", None) or []))

    grand = materials + subs_pay + expenses + advances
    return materials, subs_pay, expenses, advances, grand


def _excel_styles(ws):
    header_fill = PatternFill("solid", fgColor="1F4E79")
    header_font = Font(color="FFFFFF", bold=True)
    thin = Side(style="thin", color="3A3A3A")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    for row in ws.iter_rows(min_row=1, max_row=1):
        for cell in row:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(vertical="center")
            cell.border = border

    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.border = border
            cell.alignment = Alignment(vertical="center")


def _boq_abs_path(rel_path: str) -> str | None:
    if not rel_path:
        return None
    rel_path = rel_path.replace("\\", "/").lstrip("/")
    if not rel_path.startswith("uploads/boq/"):
        return None
    return os.path.join(current_app.root_path, "static", rel_path)


def _boq_download_name(rel_path: str, fallback_prefix: str = "boq") -> str:
    if not rel_path:
        return fallback_prefix

    rel_path = rel_path.replace("\\", "/").strip()
    filename = os.path.basename(rel_path)
    if not filename:
        return fallback_prefix

    return filename or fallback_prefix


def _parse_deposit_amount(text: str | None) -> float:
    if not text:
        return 0.0

    s = str(text).strip()
    if not s:
        return 0.0

    m = re.search(r"(-?\d[\d,]*\.?\d*)", s)
    if not m:
        return 0.0

    num_str = m.group(1).replace(",", "")
    try:
        return float(num_str)
    except Exception:
        return 0.0


def _parse_iso_date(value: str | None):
    try:
        s = (value or "").strip()
        if not s:
            return None
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _month_range(year: int, month: int):
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start, end


def _year_range(year: int):
    return date(year, 1, 1), date(year + 1, 1, 1)


def _resolve_period(prefix: str = ""):
    today = date.today()

    def g(name, default=None):
        return request.args.get(f"{prefix}{name}", default)

    def gi(name, default=None):
        return request.args.get(f"{prefix}{name}", type=int) or default

    mode = (g("mode", "month") or "month").strip().lower()
    if mode not in ("day", "month", "year", "range"):
        mode = "month"

    year = gi("year", today.year)
    month = gi("month", today.month)
    day = gi("day", today.day)

    start_date = _parse_iso_date(g("start_date"))
    end_date = _parse_iso_date(g("end_date"))

    label = ""
    range_start = None
    range_end_exclusive = None

    if mode == "day":
        try:
            range_start = date(year, month, day)
        except Exception:
            range_start = today
            year, month, day = range_start.year, range_start.month, range_start.day
        range_end_exclusive = range_start + timedelta(days=1)
        label = f"รายวัน {range_start.strftime('%d/%m/%Y')}"

    elif mode == "month":
        if month < 1 or month > 12:
            month = today.month
        range_start, range_end_exclusive = _month_range(year, month)
        label = f"รายเดือน {month:02d}/{year}"

    elif mode == "year":
        range_start, range_end_exclusive = _year_range(year)
        label = f"รายปี {year}"

    elif mode == "range":
        if start_date and end_date:
            if end_date < start_date:
                start_date, end_date = end_date, start_date
            range_start = start_date
            range_end_exclusive = end_date + timedelta(days=1)
            label = f"ช่วงวันที่ {start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}"
        elif start_date:
            range_start = start_date
            range_end_exclusive = start_date + timedelta(days=1)
            label = f"ช่วงวันที่ {start_date.strftime('%d/%m/%Y')}"
        else:
            range_start, range_end_exclusive = _month_range(year, month)
            label = f"รายเดือน {month:02d}/{year}"

    return {
        "mode": mode,
        "year": year,
        "month": month,
        "day": day,
        "start_date": start_date,
        "end_date": end_date,
        "range_start": range_start,
        "range_end_exclusive": range_end_exclusive,
        "period_label": label,
        "today": today,
    }


def _as_date(dt_value):
    if not dt_value:
        return None
    try:
        if isinstance(dt_value, datetime):
            return dt_value.date()
        return dt_value
    except Exception:
        return None




def _date_in_range(dt_value, start_inclusive, end_exclusive):
    if not dt_value or not start_inclusive or not end_exclusive:
        return False
    try:
        d = _as_date(dt_value)
        if not d:
            return False
        return start_inclusive <= d < end_exclusive
    except Exception:
        return False



def _bucket_key_for_date(dt_value, mode: str):
    d = _as_date(dt_value)
    if not d:
        return None

    if mode == "day":
        return d.strftime("%Y-%m-%d")
    if mode == "month":
        return d.strftime("%Y-%m-%d")
    if mode == "year":
        return d.strftime("%Y-%m")
    if mode == "range":
        return d.strftime("%Y-%m-%d")
    return d.strftime("%Y-%m-%d")



def _bucket_label_from_date(dt_value, mode: str):
    d = _as_date(dt_value)
    if not d:
        return "-"

    if mode == "day":
        return d.strftime("%d/%m/%Y")
    if mode == "month":
        return d.strftime("%d/%m")
    if mode == "year":
        return f"{d.month:02d}/{d.year}"
    if mode == "range":
        return d.strftime("%d/%m/%Y")
    return d.strftime("%d/%m/%Y")



def _build_buckets(range_start: date, range_end_exclusive: date, mode: str):
    buckets = []
    current = range_start

    if mode in ("day", "month", "range"):
        while current < range_end_exclusive:
            buckets.append(
                {
                    "key": _bucket_key_for_date(current, mode),
                    "label": _bucket_label_from_date(current, mode),
                    "date": current,
                }
            )
            current = current + timedelta(days=1)

    elif mode == "year":
        current = date(range_start.year, 1, 1)
        while current < range_end_exclusive:
            buckets.append(
                {
                    "key": current.strftime("%Y-%m"),
                    "label": f"{current.month:02d}/{current.year}",
                    "date": current,
                }
            )
            if current.month == 12:
                current = date(current.year + 1, 1, 1)
            else:
                current = date(current.year, current.month + 1, 1)

    return buckets


def _series_payload(range_start: date, range_end_exclusive: date, mode: str):
    buckets = _build_buckets(range_start, range_end_exclusive, mode)
    labels = [b["label"] for b in buckets]
    index_map = {b["key"]: idx for idx, b in enumerate(buckets)}
    series = [0.0 for _ in buckets]
    counts = [0 for _ in buckets]
    return buckets, labels, index_map, series, counts


def _chart_title_for_mode(mode: str):
    if mode == "day":
        return "กราฟรายวัน"
    if mode == "month":
        return "กราฟรายวันในเดือนที่เลือก"
    if mode == "year":
        return "กราฟรายเดือนในปีที่เลือก"
    if mode == "range":
        return "กราฟตามช่วงวันที่เลือก"
    return "กราฟสรุป"


def _bucket_hint_for_mode(mode: str):
    if mode == "day":
        return "แสดง 1 วัน"
    if mode == "month":
        return "แสดงรายวัน"
    if mode == "year":
        return "แสดงรายเดือน"
    if mode == "range":
        return "แสดงรายวันตามช่วงวันที่"
    return ""


def _safe_avg(total: float, count: int) -> float:
    if count <= 0:
        return 0.0
    return round(total / count, 2)


# ------------------------------------------------------------
# Routes
# ------------------------------------------------------------
@bp_pages.route("/")
def home():
    return redirect(url_for("pages.project_list"))


# -------------------------
# Projects
# -------------------------
@bp_pages.route("/projects")
def project_list():
    q = (request.args.get("q") or "").strip()

    query = Project.query.options(joinedload(Project.sales_doc))

    if q:
        like = f"%{q}%"
        query = query.filter((Project.code.ilike(like)) | (Project.name.ilike(like)))

    projects = query.order_by(Project.updated_at.desc()).limit(200).all()
    return render_template("projects/list.html", projects=projects, q=q)


@bp_pages.route("/projects/new")
def project_new():
    return render_template("projects/form_onepage.html", project=None)


@bp_pages.route("/projects/<int:pid>/edit")
def project_edit(pid: int):
    project = Project.query.options(joinedload(Project.sales_doc)).get_or_404(pid)
    return render_template("projects/form_onepage.html", project=project)


@bp_pages.route("/projects/<int:pid>")
def project_view(pid: int):
    project = Project.query.options(joinedload(Project.sales_doc)).get_or_404(pid)

    materials_total, subs_total, expenses_total, advances_total, grand_total = _project_totals(project)

    qt_doc = None
    try:
        qt_doc = getattr(project, "sales_doc", None)
    except Exception:
        qt_doc = None

    return render_template(
        "projects/view.html",
        project=project,
        qt_doc=qt_doc,
        materials_total=materials_total,
        subs_total=subs_total,
        expenses_total=expenses_total,
        advances_total=advances_total,
        grand_total=grand_total,
    )


# ------------------------------------------------------------
# Download BOQ from Project
# ------------------------------------------------------------
@bp_pages.get("/projects/<int:pid>/boq/excel")
def project_download_boq_excel(pid: int):
    project = Project.query.get_or_404(pid)

    rel = (getattr(project, "boq_excel_path", None) or "").strip()
    abs_path = _boq_abs_path(rel)
    if not abs_path or not os.path.exists(abs_path):
        abort(404)

    directory = os.path.dirname(abs_path)
    filename = os.path.basename(abs_path)
    download_name = _boq_download_name(rel, fallback_prefix=f"{project.code or 'boq'}.xlsx")
    return send_from_directory(
        directory,
        filename,
        as_attachment=True,
        download_name=download_name,
    )


@bp_pages.get("/projects/<int:pid>/boq/pdf")
def project_download_boq_pdf(pid: int):
    project = Project.query.get_or_404(pid)

    rel = (getattr(project, "boq_pdf_path", None) or "").strip()
    abs_path = _boq_abs_path(rel)
    if not abs_path or not os.path.exists(abs_path):
        abort(404)

    directory = os.path.dirname(abs_path)
    filename = os.path.basename(abs_path)
    download_name = _boq_download_name(rel, fallback_prefix=f"{project.code or 'boq'}.pdf")
    return send_from_directory(
        directory,
        filename,
        as_attachment=True,
        download_name=download_name,
    )


# ------------------------------------------------------------
# Vouchers Print
# ------------------------------------------------------------
@bp_pages.route("/projects/<int:pid>/vouchers/print", methods=["POST"])
def vouchers_print(pid: int):
    project = Project.query.get_or_404(pid)

    doc_type = (request.form.get("doc_type") or "PV").upper().strip()
    if doc_type not in ("PV", "RR", "PV_WHT"):
        doc_type = "PV"

    raw_ids = request.form.getlist("ids")
    selected_rows = []
    seen = set()

    for token in raw_ids:
        token = (token or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)

        if ":" not in token:
            continue

        kind, sid = token.split(":", 1)
        kind = kind.strip().upper()

        try:
            iid = int(sid)
        except Exception:
            continue

        if doc_type == "PV_WHT":
            if kind != "S":
                continue

            item = next(
                (
                    s
                    for s in (project.subcontractors or [])
                    if int(getattr(s, "id", 0) or 0) == iid
                ),
                None,
            )
            if not item:
                continue

            contract_amount = _num(getattr(item, "contract_amount", 0))
            withholding_rate = _num(getattr(item, "withholding_rate", 0))
            withholding_amount = _num(getattr(item, "withholding_amount", 0))
            net_pay = contract_amount - withholding_amount

            selected_rows.append(
                {
                    "kind": "S_WHT",
                    "sub_id": int(getattr(item, "id", 0) or 0),
                    "vendor_name": getattr(item, "vendor_name", "") or "ผู้รับเหมา",
                    "contract_amount": contract_amount,
                    "withholding_rate": withholding_rate,
                    "withholding_amount": withholding_amount,
                    "net_pay": net_pay,
                    "date": getattr(item, "pay_date", None),
                }
            )
            continue

        if kind == "M":
            item = next(
                (
                    m
                    for m in (project.materials or [])
                    if int(getattr(m, "id", 0) or 0) == iid
                ),
                None,
            )
            if item:
                item_name = (getattr(item, "item_name", None) or "").strip()
                item_code = (getattr(item, "item_code", None) or "").strip()
                particular = item_name or "วัสดุ"
                if item_code:
                    particular = f"{particular} ({item_code})"

                amount = _num(getattr(item, "unit_price", 0)) * _num(getattr(item, "qty", 0))

                selected_rows.append(
                    {
                        "kind": "M",
                        "title": "วัสดุ",
                        "particular": particular,
                        "ref_no": item_code,
                        "amount": amount,
                        "date": getattr(item, "tax_invoice_date", None),
                        "tax_invoice_no": getattr(item, "tax_invoice_no", "") or "",
                    }
                )

        elif kind == "S":
            item = next(
                (
                    s
                    for s in (project.subcontractors or [])
                    if int(getattr(s, "id", 0) or 0) == iid
                ),
                None,
            )
            if item:
                pay = _num(getattr(item, "contract_amount", 0)) - _num(getattr(item, "withholding_amount", 0))
                selected_rows.append(
                    {
                        "kind": "S",
                        "title": "ผู้รับเหมาช่วง",
                        "particular": getattr(item, "vendor_name", "") or "ผู้รับเหมา",
                        "ref_no": "",
                        "amount": pay,
                        "withholding_rate": _num(getattr(item, "withholding_rate", 0)),
                        "withholding_amount": _num(getattr(item, "withholding_amount", 0)),
                        "date": getattr(item, "pay_date", None),
                    }
                )

        elif kind == "E":
            item = next(
                (
                    e
                    for e in (project.expenses or [])
                    if int(getattr(e, "id", 0) or 0) == iid
                ),
                None,
            )
            if item:
                selected_rows.append(
                    {
                        "kind": "E",
                        "title": "ค่าใช้จ่ายอื่น",
                        "particular": f"{getattr(item, 'category', '') or 'อื่นๆ'} - {getattr(item, 'title', '') or ''}",
                        "ref_no": "",
                        "amount": _num(getattr(item, "amount", 0)),
                        "date": getattr(item, "expense_date", None),
                    }
                )

        elif kind == "A":
            advances = getattr(project, "advances", None) or []
            item = next(
                (
                    a
                    for a in advances
                    if int(getattr(a, "id", 0) or 0) == iid
                ),
                None,
            )
            if item:
                selected_rows.append(
                    {
                        "kind": "A",
                        "title": "เงินเบิกล่วงหน้า",
                        "particular": getattr(item, "title", "") or "",
                        "ref_no": "",
                        "amount": _num(getattr(item, "amount", 0)),
                        "date": getattr(item, "advance_date", None),
                    }
                )

    if not selected_rows:
        return redirect(url_for("pages.project_view", pid=project.id))

    return render_template(
        "projects/vouchers_print.html",
        project=project,
        doc_type=doc_type,
        rows=selected_rows,
        today=date.today(),
    )


# -------------------------
# Dashboard (โครงการ)
# -------------------------
@bp_pages.route("/dashboard")
def dashboard():
    params = _resolve_period()
    mode = params["mode"]
    year = params["year"]
    month = params["month"]
    day = params["day"]
    start_date = params["start_date"]
    end_date = params["end_date"]
    range_start = params["range_start"]
    range_end_exclusive = params["range_end_exclusive"]
    period_label = params["period_label"]
    today = params["today"]

    years = list(range(today.year - 5, today.year + 2))

    projects = Project.query.options(joinedload(Project.sales_doc)).all()

    filtered_projects = []
    for p in projects:
        ref_date = p.start_date or p.created_at
        if _date_in_range(ref_date, range_start, range_end_exclusive):
            filtered_projects.append(p)

    tot_m = tot_s = tot_e = tot_a = tot_g = 0.0
    tot_income = 0.0
    rows = []

    buckets, labels, index_map, series, counts = _series_payload(range_start, range_end_exclusive, mode)

    for p in filtered_projects:
        m, s, e, a, g = _project_totals(p)
        tot_m += m
        tot_s += s
        tot_e += e
        tot_a += a
        tot_g += g

        doc = getattr(p, "sales_doc", None)
        if doc and getattr(doc, "status", None) == "APPROVED":
            try:
                tot_income += float(getattr(doc, "grand_total", 0) or 0)
            except Exception:
                pass

        ref_date = p.start_date or p.created_at
        bucket_key = _bucket_key_for_date(ref_date, mode)
        idx = index_map.get(bucket_key)
        if idx is not None:
            series[idx] += g
            counts[idx] += 1

        rows.append(
            {
                "id": p.id,
                "code": p.code,
                "name": p.name,
                "materials": m,
                "subs": s,
                "expenses": e,
                "advances": a,
                "total": g,
            }
        )

    rows.sort(key=lambda r: r["total"], reverse=True)
    top5 = rows[:5]

    profit_loss = tot_income - tot_g
    max_series_value = max(series) if series else 0.0

    class Totals:
        def __init__(self, m, s, e, a, g):
            self.materials = m
            self.subs = s
            self.expenses = e
            self.advances = a
            self.grand = g

    summary_cards = [
        {"label": "รายรับรวม", "value": round(tot_income, 2)},
        {"label": "ต้นทุนรวม", "value": round(tot_g, 2)},
        {"label": "กำไร / ขาดทุน", "value": round(profit_loss, 2)},
        {"label": "จำนวนโครงการ", "value": len(filtered_projects)},
    ]

    return render_template(
        "dashboard.html",
        mode=mode,
        year=year,
        month=month,
        day=day,
        start_date=start_date.isoformat() if start_date else "",
        end_date=end_date.isoformat() if end_date else "",
        period_label=period_label,
        years=years,
        totals=Totals(tot_m, tot_s, tot_e, tot_a, tot_g),
        top5=top5,
        total_income=round(tot_income, 2),
        profit_loss=round(profit_loss, 2),
        labels=labels,
        series=[round(x, 2) for x in series],
        counts=counts,
        chart_title=_chart_title_for_mode(mode),
        bucket_hint=_bucket_hint_for_mode(mode),
        summary_cards=summary_cards,
        max_series_value=round(max_series_value, 2),
        avg_per_bucket=_safe_avg(sum(series), len([x for x in series if x > 0])),
        top_projects=top5,
    )


# -------------------------
# Export Excel
# -------------------------
@bp_pages.route("/projects/<int:pid>/export.xlsx")
def project_export_xlsx(pid: int):
    project = Project.query.get_or_404(pid)
    materials_total, subs_total, expenses_total, advances_total, grand_total = _project_totals(project)

    wb = Workbook()
    ws = wb.active
    ws.title = "Project"

    ws.append(
        [
            "รหัสโครงการ",
            "ชื่อโครงการ",
            "สถานะ",
            "ลูกค้า",
            "สถานที่",
            "วันเริ่ม",
            "วันสิ้นสุด",
            "วันทำงาน",
            "ค่าวัสดุ",
            "ผู้รับเหมาช่วง",
            "ค่าใช้จ่ายอื่น",
            "เงินเบิกล่วงหน้า",
            "รวมทั้งหมด",
        ]
    )
    ws.append(
        [
            project.code,
            project.name,
            project.status,
            project.customer_name or "",
            project.location or "",
            str(project.start_date or ""),
            str(project.end_date or ""),
            project.work_days or 0,
            materials_total,
            subs_total,
            expenses_total,
            advances_total,
            grand_total,
        ]
    )

    _excel_styles(ws)

    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)

    return send_file(
        bio,
        as_attachment=True,
        download_name=f"project_{project.code}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@bp_pages.route("/dashboard/export.xlsx")
def dashboard_export_xlsx():
    params = _resolve_period()
    range_start = params["range_start"]
    range_end_exclusive = params["range_end_exclusive"]
    mode = params["mode"]
    year = params["year"]
    month = params["month"]
    day = params["day"]

    projects = Project.query.all()
    filtered_projects = []

    for p in projects:
        ref_date = p.start_date or p.created_at
        if _date_in_range(ref_date, range_start, range_end_exclusive):
            filtered_projects.append(p)

    wb = Workbook()
    ws = wb.active
    ws.title = "Dashboard"

    ws.append(["รหัส", "ชื่อโครงการ", "ค่าวัสดุ", "ผู้รับเหมาช่วง", "ค่าใช้จ่ายอื่น", "เงินเบิกล่วงหน้า", "รวม"])

    for p in filtered_projects:
        m, s, e, a, g = _project_totals(p)
        ws.append([p.code, p.name, m, s, e, a, g])

    _excel_styles(ws)

    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)

    suffix = f"{mode}_{year}_{month or 'all'}_{day or 'all'}"
    return send_file(
        bio,
        as_attachment=True,
        download_name=f"dashboard_{suffix}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ------------------------------------------------------------
# Finance dashboards
# ------------------------------------------------------------
@bp_pages.get("/dashboard/in come")
def dashboard_income_typo_redirect():
    return redirect(url_for("pages.dashboard_income"))


@bp_pages.get("/dashboard/income")
def dashboard_income():
    params = _resolve_period(prefix="income_")
    mode = params["mode"]
    year = params["year"]
    month = params["month"]
    day = params["day"]
    start_date = params["start_date"]
    end_date = params["end_date"]
    range_start = params["range_start"]
    range_end_exclusive = params["range_end_exclusive"]
    period_label = params["period_label"]
    today = params["today"]

    q = (
        SalesDoc.query.filter(SalesDoc.doc_type == "IV")
        .filter(SalesDoc.status == "APPROVED")
        .filter(SalesDoc.issue_date.isnot(None))
    )
    docs = q.all()

    buckets, labels, index_map, series, counts = _series_payload(range_start, range_end_exclusive, mode)

    total_income = 0.0
    total_vat = 0.0
    total_wht = 0.0
    total_net = 0.0
    total_docs = 0
    doc_rows = []

    for d in docs:
        if not _date_in_range(d.issue_date, range_start, range_end_exclusive):
            continue

        gross = _num(getattr(d, "gross_total", 0))
        vat = _num(getattr(d, "vat_amount", 0))
        wht = _num(getattr(d, "wht_amount", 0))
        net_pay = _num(getattr(d, "grand_total", 0))

        total_income += gross
        total_vat += vat
        total_wht += wht
        total_net += net_pay
        total_docs += 1

        bucket_key = _bucket_key_for_date(d.issue_date, mode)
        idx = index_map.get(bucket_key)
        if idx is not None:
            series[idx] += gross
            counts[idx] += 1

        doc_rows.append(
            {
                "doc_no": getattr(d, "doc_no", "") or "-",
                "customer_name": getattr(d, "customer_name", "") or "-",
                "issue_date": getattr(d, "issue_date", None),
                "gross_total": gross,
                "vat_amount": vat,
                "wht_amount": wht,
                "grand_total": net_pay,
            }
        )

    doc_rows.sort(key=lambda x: x["gross_total"], reverse=True)
    top_docs = doc_rows[:5]

    years = list(range(today.year - 5, today.year + 2))
    max_series_value = max(series) if series else 0.0

    summary_cards = [
        {"label": "รายรับรวม", "value": round(total_income, 2)},
        {"label": "VAT", "value": round(total_vat, 2)},
        {"label": "หัก ณ ที่จ่าย", "value": round(total_wht, 2)},
        {"label": "จำนวนเอกสาร", "value": total_docs},
    ]

    return render_template(
        "dashboard_income.html",
        mode=mode,
        year=year,
        month=month,
        day=day,
        start_date=start_date.isoformat() if start_date else "",
        end_date=end_date.isoformat() if end_date else "",
        period_label=period_label,
        years=years,
        labels=labels,
        series=[round(x, 2) for x in series],
        counts=counts,
        total_income=round(total_income, 2),
        total_vat=round(total_vat, 2),
        total_wht=round(total_wht, 2),
        total_net=round(total_net, 2),
        total_docs=total_docs,
        chart_title=_chart_title_for_mode(mode),
        bucket_hint=_bucket_hint_for_mode(mode),
        summary_cards=summary_cards,
        max_series_value=round(max_series_value, 2),
        avg_per_bucket=_safe_avg(sum(series), len([x for x in series if x > 0])),
        top_docs=top_docs,
    )


@bp_pages.get("/dashboard/expense")
def dashboard_expense():
    params = _resolve_period(prefix="expense_")
    mode = params["mode"]
    year = params["year"]
    month = params["month"]
    day = params["day"]
    start_date = params["start_date"]
    end_date = params["end_date"]
    range_start = params["range_start"]
    range_end_exclusive = params["range_end_exclusive"]
    period_label = params["period_label"]
    today = params["today"]

    mats = MaterialItem.query.all()
    subs = SubcontractorPayment.query.all()
    oth = OtherExpense.query.all()
    adv = AdvanceExpense.query.all()

    buckets, labels, index_map, series, counts = _series_payload(range_start, range_end_exclusive, mode)

    total_materials = 0.0
    total_subs = 0.0
    total_other = 0.0
    total_adv = 0.0
    total_expense = 0.0
    total_rows = 0

    category_totals = {
        "วัสดุ": 0.0,
        "ผู้รับเหมาช่วง": 0.0,
        "ค่าใช้จ่ายอื่น": 0.0,
        "เงินเบิกล่วงหน้า": 0.0,
    }

    def _acc(dt, amount):
        nonlocal total_expense, total_rows
        if not _date_in_range(dt, range_start, range_end_exclusive):
            return

        amt = _num(amount)
        total_expense += amt
        total_rows += 1

        bucket_key = _bucket_key_for_date(dt, mode)
        idx = index_map.get(bucket_key)
        if idx is not None:
            series[idx] += amt
            counts[idx] += 1

    for it in mats:
        dt = _pick_month_date(it, "created_at")
        amt = _num(getattr(it, "unit_price", 0)) * _num(getattr(it, "qty", 0))
        if _date_in_range(dt, range_start, range_end_exclusive):
            total_materials += amt
            category_totals["วัสดุ"] += amt
        _acc(dt, amt)

    for it in subs:
        dt = _pick_month_date(it, "pay_date", "created_at")
        amt = max(0.0, _num(getattr(it, "contract_amount", 0)) - _num(getattr(it, "withholding_amount", 0)))
        if _date_in_range(dt, range_start, range_end_exclusive):
            total_subs += amt
            category_totals["ผู้รับเหมาช่วง"] += amt
        _acc(dt, amt)

    for it in oth:
        dt = _pick_month_date(it, "expense_date", "created_at")
        amt = _num(getattr(it, "amount", 0))
        if _date_in_range(dt, range_start, range_end_exclusive):
            total_other += amt
            category_totals["ค่าใช้จ่ายอื่น"] += amt
        _acc(dt, amt)

    for it in adv:
        dt = _pick_month_date(it, "advance_date", "created_at")
        amt = _num(getattr(it, "amount", 0))
        if _date_in_range(dt, range_start, range_end_exclusive):
            total_adv += amt
            category_totals["เงินเบิกล่วงหน้า"] += amt
        _acc(dt, amt)

    years = list(range(today.year - 5, today.year + 2))
    max_series_value = max(series) if series else 0.0

    summary_cards = [
        {"label": "รายจ่ายรวม", "value": round(total_expense, 2)},
        {"label": "วัสดุ", "value": round(total_materials, 2)},
        {"label": "ผู้รับเหมาช่วง", "value": round(total_subs, 2)},
        {"label": "จำนวนรายการ", "value": total_rows},
    ]

    category_rows = [
        {"label": k, "value": round(v, 2)}
        for k, v in sorted(category_totals.items(), key=lambda x: x[1], reverse=True)
    ]

    return render_template(
        "dashboard_expense.html",
        mode=mode,
        year=year,
        month=month,
        day=day,
        start_date=start_date.isoformat() if start_date else "",
        end_date=end_date.isoformat() if end_date else "",
        period_label=period_label,
        years=years,
        labels=labels,
        series=[round(x, 2) for x in series],
        counts=counts,
        total_expense=round(total_expense, 2),
        total_materials=round(total_materials, 2),
        total_subs=round(total_subs, 2),
        total_other=round(total_other, 2),
        total_advances=round(total_adv, 2),
        total_rows=total_rows,
        chart_title=_chart_title_for_mode(mode),
        bucket_hint=_bucket_hint_for_mode(mode),
        summary_cards=summary_cards,
        max_series_value=round(max_series_value, 2),
        avg_per_bucket=_safe_avg(sum(series), len([x for x in series if x > 0])),
        category_rows=category_rows,
    )


@bp_pages.get("/dashboard/finance")
def dashboard_finance_redirect():
    return redirect(url_for("pages.dashboard_income"))


# ------------------------------------------------------------
# Deposit Notifications
# ------------------------------------------------------------
@bp_pages.get("/deposits/notifications")
def deposit_notifications():
    q = (request.args.get("q") or "").strip()

    query = Project.query.options(joinedload(Project.sales_doc))
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Project.code.ilike(like),
                Project.name.ilike(like),
                Project.customer_name.ilike(like),
            )
        )

    projects = query.order_by(Project.updated_at.desc()).all()

    rows = []
    sum_not_returned = 0.0
    sum_returned = 0.0
    cnt_no_deposit = 0
    cnt_returned = 0

    for p in projects:
        doc = getattr(p, "sales_doc", None)

        customer_name = (
            (getattr(p, "customer_name", None) or "").strip()
            or (getattr(doc, "customer_name", None) if doc else None)
            or "-"
        )

        deposit_note = getattr(doc, "deposit_note", None) if doc else None
        dep_amount_f = _parse_deposit_amount(deposit_note)

        end_date = getattr(doc, "warranty_end_date", None) if doc else None
        returned = bool(getattr(p, "deposit_returned", False))

        if dep_amount_f <= 0:
            cnt_no_deposit += 1
        else:
            if returned:
                sum_returned += dep_amount_f
                cnt_returned += 1
            else:
                sum_not_returned += dep_amount_f

        rows.append(
            {
                "id": p.id,
                "code": p.code,
                "project_name": p.name,
                "customer_name": customer_name,
                "deposit_amount": dep_amount_f,
                "end_date": end_date,
                "returned": returned,
            }
        )

    return render_template(
        "notifications/deposits.html",
        q=q,
        rows=rows,
        sum_not_returned=round(sum_not_returned, 2),
        sum_returned=round(sum_returned, 2),
        cnt_no_deposit=cnt_no_deposit,
        cnt_returned=cnt_returned,
    )


@bp_pages.post("/deposits/<int:pid>/return")
def deposit_mark_returned(pid: int):
    p = Project.query.get_or_404(pid)
    p.deposit_returned = True

    try:
        p.deposit_returned_at = datetime.utcnow()
    except Exception:
        p.deposit_returned_at = date.today()

    db.session.commit()
    return redirect(url_for("pages.deposit_notifications"))
