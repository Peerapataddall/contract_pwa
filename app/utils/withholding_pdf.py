from __future__ import annotations

import os
import tempfile
from io import BytesIO
from datetime import date
from decimal import Decimal

from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, ArrayObject, BooleanObject


# =========================================================
# CONFIG
# =========================================================
DEBUG_DRAW = False
DEBUG_GRID_STEP = 25

OFFSET_X = 0
OFFSET_Y = 0

TEMPLATE_REL = os.path.join("static", "forms", "withholding_50twi.pdf")

FONT_REL = os.path.join("static", "fonts", "THSarabunNew.ttf")
FONT_NAME = "THSarabunNew"

BASE_FONT_SIZE = 12

BOX_H_TAX = 16
BOX_H_DATE = 16
BASELINE_TWEAK = 0.28

# ✅ แยกช่องว่าง “กลุ่มเลข 13 หลัก” ระหว่าง payer/payee
TAX_GROUP_GAP_W_PAYER = 0.2
TAX_GROUP_GAP_W_PAYEE = 0.1

# =========================================================
# ✅ จุดที่ 1 (เครื่องหมายถูก “(7) ภ.ง.ด.53”) — absolute
# ปรับแค่ DX/DY:
#   +DX = ไปขวา, +DY = ขึ้น (หน่วย pt)
# =========================================================
CHK_PND53_ABS_X = 408
CHK_PND53_ABS_Y = 517
CHK_PND53_DX = -15
CHK_PND53_DY = 65

# =========================================================
# ✅ จุดที่ 2 (เครื่องหมายถูก “(4) ภ.ง.ด.3”) — absolute (ล็อกแล้ว ไม่ต้องยุ่ง)
# ปรับแค่ DX/DY:
# =========================================================
CHK_PND3_ABS_X = 408
CHK_PND3_ABS_Y = 542
CHK_PND3_DX = 62
CHK_PND3_DY = 60


# ---------------------------------------------------------
# POS (หน่วย pt)  (ค่า base ก่อน apply shifts)
# ---------------------------------------------------------
POS = {
    # ===== ผู้มีหน้าที่หักภาษี ณ ที่จ่าย =====
    "payer_name": (90, 736),
    "payer_addr": (90, 698),

    "payer_tax_boxes": (405, 725),
    "payer_tax_box_w": 15.3,
    "payer_tax_box_h": BOX_H_TAX,

    # ===== ผู้ถูกหักภาษี ณ ที่จ่าย =====
    "payee_name": (90, 642),
    "payee_addr": (90, 606),

    "payee_tax_boxes": (405, 618),
    "payee_tax_box_w": 15.3,
    "payee_tax_box_h": BOX_H_TAX,

    # ===== กล่องติ๊กในหัวข้อ "ในแบบ" =====
    # NOTE: เรา “ไม่ใช้แล้ว” แต่ยังเก็บไว้เพื่อไม่ให้โค้ดเดิมพัง
    "chk_pnd3_box": (408, 542),
    "chk_pnd53_box": (408, 517),

    # ===== กล่องติ๊กด้านล่าง "ผู้จ่ายเงิน (1) หัก ณ ที่จ่าย" =====
    "chk_paytype_1_box": (98, 147),

    # ===== ตารางรายการ: วันที่จ่าย (เป็นข้อความ dd/mm/yyyy) =====
    "row_paydate_text": (430, 357),

    # ===== เงินในตาราง (ชิดขวา) =====
    "row_base_amt_right": 520,
    "row_wht_amt_right": 585,
    "row_money_y": 260,

    # ===== สรุปรวมด้านล่าง (ชิดขวา) =====
    "sum_base_amt_right": 520,
    "sum_wht_amt_right": 585,
    "sum_money_y": 245,

    # ===== ภาษีหักเป็นตัวอักษร =====
    "wht_text": (155, 225),

    # ===== วันที่ลงชื่อ (แบบช่อง dd/mm/yyyy) =====
    "sign_date_start": (250, 105),
    "sign_date_box_w": 13.8,
    "sign_date_box_h": BOX_H_DATE,
}


# =========================================================
# APPLY SHIFTS
# =========================================================
def _apply_shifts():
    # --------------------------
    # ชุดเดิมสะสม (ตามโค้ดที่คุณส่งมา)
    # (เราไม่ได้ลบ/เปลี่ยน เพื่อไม่ให้ตำแหน่งอื่นขยับ)
    # --------------------------
    POS["payer_addr"] = (POS["payer_addr"][0], POS["payer_addr"][1] + 10)
    POS["payer_tax_boxes"] = (POS["payer_tax_boxes"][0] + 10, POS["payer_tax_boxes"][1] + 5)

    POS["payee_name"] = (POS["payee_name"][0], POS["payee_name"][1] + 10)
    POS["payee_addr"] = (POS["payee_addr"][0], POS["payee_addr"][1] + 15)
    POS["payee_tax_boxes"] = (POS["payee_tax_boxes"][0], POS["payee_tax_boxes"][1] + 20)

    POS["chk_pnd3_box"] = (POS["chk_pnd3_box"][0] + 15, POS["chk_pnd3_box"][1] + 20)
    POS["chk_paytype_1_box"] = (POS["chk_paytype_1_box"][0] + 15, POS["chk_paytype_1_box"][1] + 20)

    POS["row_paydate_text"] = (POS["row_paydate_text"][0] - 20, POS["row_paydate_text"][1] - 40)

    POS["payer_tax_boxes"] = (POS["payer_tax_boxes"][0] - 20, POS["payer_tax_boxes"][1] + 20)
    POS["payee_name"] = (POS["payee_name"][0], POS["payee_name"][1] + 10)
    POS["payee_addr"] = (POS["payee_addr"][0], POS["payee_addr"][1] + 10)
    POS["payee_tax_boxes"] = (POS["payee_tax_boxes"][0] - 15, POS["payee_tax_boxes"][1] + 10)
    POS["chk_pnd3_box"] = (POS["chk_pnd3_box"][0] + 15, POS["chk_pnd3_box"][1] + 15)
    POS["chk_paytype_1_box"] = (POS["chk_paytype_1_box"][0] + 15, POS["chk_paytype_1_box"][1] + 15)
    POS["row_paydate_text"] = (POS["row_paydate_text"][0] - 10, POS["row_paydate_text"][1] - 20)

    POS["payer_tax_boxes"] = (POS["payer_tax_boxes"][0] - 10, POS["payer_tax_boxes"][1] - 5)
    POS["payee_tax_boxes"] = (POS["payee_tax_boxes"][0] - 20, POS["payee_tax_boxes"][1] + 20)
    POS["row_paydate_text"] = (POS["row_paydate_text"][0] - 20, POS["row_paydate_text"][1] - 30)
    POS["chk_paytype_1_box"] = (POS["chk_paytype_1_box"][0] - 20, POS["chk_paytype_1_box"][1] - 40)
    POS["wht_text"] = (POS["wht_text"][0] + 30, POS["wht_text"][1] - 30)
    POS["sign_date_start"] = (POS["sign_date_start"][0] + 30, POS["sign_date_start"][1] - 20)

    POS["row_base_amt_right"] = POS["row_base_amt_right"] - 40
    POS["row_wht_amt_right"] = POS["row_wht_amt_right"] - 40
    POS["row_money_y"] = POS["row_money_y"] - 30
    POS["wht_text"] = (POS["wht_text"][0], POS["wht_text"][1] - 25)
    POS["sign_date_start"] = (POS["sign_date_start"][0] + 40, POS["sign_date_start"][1] - 25)

    POS["payer_tax_boxes"] = (POS["payer_tax_boxes"][0] - 10, POS["payer_tax_boxes"][1])
    POS["row_money_y"] = POS["row_money_y"] - 50
    POS["sum_base_amt_right"] = POS["sum_base_amt_right"] - 30
    POS["sum_wht_amt_right"] = POS["sum_wht_amt_right"] - 30
    POS["sum_money_y"] = POS["sum_money_y"] - 20
    POS["chk_paytype_1_box"] = (POS["chk_paytype_1_box"][0] - 20, POS["chk_paytype_1_box"][1] - 5)
    POS["wht_text"] = (POS["wht_text"][0], POS["wht_text"][1] - 8)
    POS["sign_date_start"] = (POS["sign_date_start"][0] + 10, POS["sign_date_start"][1] + 8)

    # ======================================================
    # ✅ ปรับตามคำสั่ง “ก่อนหน้านี้”
    # ======================================================
    POS["payee_tax_boxes"] = (POS["payee_tax_boxes"][0], POS["payee_tax_boxes"][1] + 5)
    POS["row_paydate_text"] = (POS["row_paydate_text"][0] - 15, POS["row_paydate_text"][1] - 20)
    POS["chk_paytype_1_box"] = (POS["chk_paytype_1_box"][0] - 5, POS["chk_paytype_1_box"][1] - 6)
    POS["sign_date_start"] = (POS["sign_date_start"][0] + 5, POS["sign_date_start"][1] + 3)

    # ======================================================
    # ✅ ปรับตามคำสั่ง “รอบนี้” (ก่อนหน้ารอบล่าสุด)
    # ======================================================
    POS["payer_tax_boxes"] = (POS["payer_tax_boxes"][0] - 5, POS["payer_tax_boxes"][1])
    POS["row_paydate_text"] = (POS["row_paydate_text"][0] - 10, POS["row_paydate_text"][1] - 15)
    POS["chk_paytype_1_box"] = (POS["chk_paytype_1_box"][0], POS["chk_paytype_1_box"][1] - 5)

    # ======================================================
    # ✅ รอบล่าสุดตามที่คุย: จุดที่ 2 + วันที่ลงชื่อ (ถ้ามี)
    # ======================================================
    POS["chk_paytype_1_box"] = (POS["chk_paytype_1_box"][0], POS["chk_paytype_1_box"][1] - 5)
    POS["sign_date_start"] = (POS["sign_date_start"][0] + 5, POS["sign_date_start"][1])


_apply_shifts()


# =========================================================
# Helpers (Paths / Font)
# =========================================================
def _app_dir() -> str:
    return os.path.dirname(os.path.dirname(__file__))


def _abs_path(rel: str) -> str:
    return os.path.join(_app_dir(), rel)


def _register_thai_font() -> str:
    font_path = _abs_path(FONT_REL)
    if os.path.exists(font_path):
        try:
            pdfmetrics.getFont(FONT_NAME)
            return FONT_NAME
        except Exception:
            pdfmetrics.registerFont(TTFont(FONT_NAME, font_path))
            return FONT_NAME
    return "Helvetica"


def _xy(key: str):
    x, y = POS[key]
    return (x + OFFSET_X, y + OFFSET_Y)


def _xy_pnd53_abs():
    # ✅ ตำแหน่งติ๊ก (7) ภ.ง.ด.53 แบบ absolute
    x = CHK_PND53_ABS_X + CHK_PND53_DX + OFFSET_X
    y = CHK_PND53_ABS_Y + CHK_PND53_DY + OFFSET_Y
    return x, y


def _xy_pnd3_abs():
    # ✅ ตำแหน่งติ๊ก (4) ภ.ง.ด.3 แบบ absolute (ล็อกแล้ว)
    x = CHK_PND3_ABS_X + CHK_PND3_DX + OFFSET_X
    y = CHK_PND3_ABS_Y + CHK_PND3_DY + OFFSET_Y
    return x, y


# =========================================================
# Format / Drawing
# =========================================================
def _digits_only(s: str) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())


def _fmt_money(v) -> str:
    try:
        if v is None:
            return "0.00"
        if isinstance(v, Decimal):
            x = float(v)
        else:
            x = float(str(v).replace(",", "").strip())
        return f"{x:,.2f}"
    except Exception:
        return "0.00"


def _draw_grid(c: canvas.Canvas, page_w: float, page_h: float, step: int = 25):
    c.saveState()
    c.setLineWidth(0.25)
    c.setFont("Helvetica", 7)

    x = 0
    while x <= page_w:
        c.line(x, 0, x, page_h)
        c.drawString(x + 2, page_h - 10, str(int(x)))
        x += step

    y = 0
    while y <= page_h:
        c.line(0, y, page_w, y)
        c.drawString(2, y + 2, str(int(y)))
        y += step

    c.restoreState()


def _marker(c: canvas.Canvas, x: float, y: float, label: str = ""):
    c.saveState()
    c.setLineWidth(1)
    c.circle(x, y, 2, stroke=1, fill=0)
    c.setFont("Helvetica", 7)
    if label:
        c.drawString(x + 4, y + 2, label)
    c.restoreState()


def _draw_text(c: canvas.Canvas, font: str, x: float, y: float, text: str, size: int = BASE_FONT_SIZE):
    c.setFont(font, size)
    c.drawString(x, y, text or "")


def _draw_text_wrapped(
    c: canvas.Canvas,
    font: str,
    x: float,
    y: float,
    text: str,
    max_width: float,
    size: int = BASE_FONT_SIZE,
    max_lines: int = 2,
):
    if not text:
        return
    c.setFont(font, size)
    words = (text or "").replace("\n", " ").split()
    lines = []
    cur = ""

    for w in words:
        test = (cur + " " + w).strip()
        if pdfmetrics.stringWidth(test, font, size) <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
            if len(lines) >= max_lines:
                break

    if len(lines) < max_lines and cur:
        lines.append(cur)

    yy = y
    for ln in lines[:max_lines]:
        c.drawString(x, yy, ln)
        yy -= (size + 2)


def _draw_check_in_box(
    c: canvas.Canvas,
    box_x: float,
    box_y: float,
    box_size: float = 14,
):
    c.saveState()
    pad = box_size * 0.22
    x1 = box_x + pad
    y1 = box_y + box_size * 0.45
    x2 = box_x + box_size * 0.42
    y2 = box_y + pad
    x3 = box_x + box_size - pad
    y3 = box_y + box_size - pad

    c.setLineWidth(1.8)
    c.line(x1, y1, x2, y2)
    c.line(x2, y2, x3, y3)
    c.restoreState()


def _draw_digits_in_boxes(
    c: canvas.Canvas,
    font: str,
    digits: str,
    x: float,
    y: float,
    box_w: float,
    box_h: float,
    n: int = 13,
    size: int = 12,
    group_gaps: tuple[int, ...] = (1, 5, 10, 12),
    gap_w: float = 6.0,
):
    d = _digits_only(digits)
    d = (d + (" " * n))[:n]
    c.setFont(font, size)

    xi = x
    for i in range(n):
        ch = d[i].strip()
        if ch:
            cx = xi + (box_w / 2.0)
            baseline = y + (box_h / 2.0) - (size * BASELINE_TWEAK)
            c.drawCentredString(cx, baseline, ch)

        xi += box_w
        if (i + 1) in group_gaps:
            xi += gap_w


def _draw_date_ddmmyyyy_boxes(
    c: canvas.Canvas,
    font: str,
    dt: date,
    x: float,
    y: float,
    box_w: float,
    box_h: float,
    size: int = 12,
):
    s = dt.strftime("%d/%m/%Y")
    c.setFont(font, size)

    xi = x
    for ch in s:
        if ch == "/":
            xi += box_w * 0.85
            continue
        cx = xi + (box_w / 2.0)
        baseline = y + (box_h / 2.0) - (size * BASELINE_TWEAK)
        c.drawCentredString(cx, baseline, ch)
        xi += box_w


def _draw_date_string(
    c: canvas.Canvas,
    font: str,
    dt: date,
    x: float,
    y: float,
    size: int = 12,
):
    c.setFont(font, size)
    c.drawString(x, y, dt.strftime("%d/%m/%Y"))


# =========================================================
# Thai Baht Text
# =========================================================
_TH_NUM = ["ศูนย์", "หนึ่ง", "สอง", "สาม", "สี่", "ห้า", "หก", "เจ็ด", "แปด", "เก้า"]
_TH_UNIT = ["", "สิบ", "ร้อย", "พัน", "หมื่น", "แสน", "ล้าน"]


def _thai_read_int(n: int) -> str:
    if n == 0:
        return _TH_NUM[0]

    def read_under_million(x: int) -> str:
        s = ""
        digits = list(map(int, str(x)))
        L = len(digits)
        for i, d in enumerate(digits):
            pos = L - i - 1
            if d == 0:
                continue
            if pos == 1:
                if d == 1:
                    s += "สิบ"
                elif d == 2:
                    s += "ยี่สิบ"
                else:
                    s += _TH_NUM[d] + "สิบ"
            elif pos == 0:
                if d == 1 and L >= 2 and digits[-2] != 0:
                    s += "เอ็ด"
                else:
                    s += _TH_NUM[d]
            else:
                s += _TH_NUM[d] + _TH_UNIT[pos]
        return s

    parts = []
    million = 1_000_000
    while n > 0:
        n, rem = divmod(n, million)
        parts.append(rem)

    out = ""
    for i in range(len(parts) - 1, -1, -1):
        rem = parts[i]
        if rem == 0:
            continue
        chunk = read_under_million(rem)
        if i >= 1:
            out += chunk + "ล้าน"
        else:
            out += chunk
    return out or _TH_NUM[0]


def thai_baht_text(amount: Decimal) -> str:
    try:
        x = Decimal(amount or 0).quantize(Decimal("0.01"))
    except Exception:
        x = Decimal("0.00")

    baht = int(x)
    satang = int((x - Decimal(baht)) * 100)

    baht_txt = _thai_read_int(baht) + "บาท"
    if satang == 0:
        return baht_txt + "ถ้วน"
    return baht_txt + _thai_read_int(satang) + "สตางค์"


# =========================================================
# PDF: remove original marks (annots/acroform)
# =========================================================
def _strip_page_annotations(page):
    # ลบ annotation ที่แปะอยู่บนหน้า (รวมถึง checkbox appearance ที่มากับไฟล์)
    try:
        if "/Annots" in page:
            page[NameObject("/Annots")] = ArrayObject()
    except Exception:
        pass


def _strip_acroform(reader: PdfReader):
    # เคลียร์ AcroForm fields จากไฟล์ต้นฉบับ (กันติ๊กเดิม “ถูกฝัง” มาด้วย)
    try:
        root = reader.trailer["/Root"]
        if "/AcroForm" in root:
            acro = root["/AcroForm"]
            try:
                acro[NameObject("/Fields")] = ArrayObject()
            except Exception:
                pass
            try:
                acro[NameObject("/NeedAppearances")] = BooleanObject(False)
            except Exception:
                pass
    except Exception:
        pass


# =========================================================
# Public API
# =========================================================
def build_withholding_pdf(doc) -> str:
    font = _register_thai_font()

    template_path = _abs_path(TEMPLATE_REL)
    if not os.path.exists(template_path):
        raise FileNotFoundError(
            f"Missing withholding template PDF: {template_path}\n"
            f"→ กรุณาวางไฟล์ฟอร์มไว้ที่ app/{TEMPLATE_REL}"
        )

    template_reader = PdfReader(template_path)
    _strip_acroform(template_reader)

    base_page = template_reader.pages[0]
    _strip_page_annotations(base_page)

    page_w = float(base_page.mediabox.width)
    page_h = float(base_page.mediabox.height)

    payer_name = getattr(doc, "payer_name", "") or ""
    payer_addr = getattr(doc, "payer_address", "") or ""
    payer_tax = getattr(doc, "payer_tax_id", "") or ""

    payee_name = ""
    payee_addr = ""
    payee_tax = ""

    payee_kind = (getattr(doc, "payee_kind", "") or "").upper()
    if payee_kind == "PERSON" and getattr(doc, "payee_person", None):
        p = doc.payee_person
        payee_name = getattr(p, "full_name", "") or ""
        payee_addr = getattr(p, "address", "") or ""
        payee_tax = getattr(p, "tax_id", "") or ""
    elif payee_kind == "ENTITY" and getattr(doc, "payee_entity", None):
        e = doc.payee_entity
        payee_name = getattr(e, "company_name", "") or ""
        payee_addr = getattr(e, "address", "") or ""
        payee_tax = getattr(e, "tax_id", "") or ""

    dt = getattr(doc, "payment_date", None) or date.today()
    base_amount = getattr(doc, "base_amount", Decimal("0")) or Decimal("0")
    wht_amount = getattr(doc, "wht_amount", Decimal("0")) or Decimal("0")

    # ✅ robust form_type: รองรับ PND.3 / ภงด.3 / PND.53 / ภงด.53 และ “ไม่เดา 53 อัตโนมัติ”
    ft = (getattr(doc, "form_type", "") or "").upper()
    ft = ft.replace(".", "").replace(" ", "")

    is_pnd3 = ft in ("PND3", "P3", "3", "ภงด3")
    is_pnd53 = ft in ("PND53", "53", "ภงด53")

    overlay_buf = BytesIO()
    c = canvas.Canvas(overlay_buf, pagesize=(page_w, page_h))

    if DEBUG_DRAW:
        _draw_grid(c, page_w, page_h, step=DEBUG_GRID_STEP)
        for k, v in POS.items():
            if isinstance(v, tuple) and len(v) == 2 and not k.endswith("_right"):
                x, y = _xy(k)
                _marker(c, x, y, k)

        mx3, my3 = _xy_pnd3_abs()
        _marker(c, mx3, my3, "CHK_PND3_ABS")
        mx, my = _xy_pnd53_abs()
        _marker(c, mx, my, "CHK_PND53_ABS")

    # payer
    _draw_text(c, font, *_xy("payer_name"), payer_name, 14)
    _draw_text_wrapped(c, font, *_xy("payer_addr"), payer_addr, max_width=315, size=12, max_lines=2)

    x0, y0 = _xy("payer_tax_boxes")
    _draw_digits_in_boxes(
        c, font, payer_tax,
        x0, y0,
        POS["payer_tax_box_w"], POS["payer_tax_box_h"],
        n=13, size=14, gap_w=TAX_GROUP_GAP_W_PAYER
    )

    # payee
    _draw_text(c, font, *_xy("payee_name"), payee_name, 14)
    _draw_text_wrapped(c, font, *_xy("payee_addr"), payee_addr, max_width=315, size=12, max_lines=2)

    x1, y1 = _xy("payee_tax_boxes")
    _draw_digits_in_boxes(
        c, font, payee_tax,
        x1, y1,
        POS["payee_tax_box_w"], POS["payee_tax_box_h"],
        n=13, size=14, gap_w=TAX_GROUP_GAP_W_PAYEE
    )

    # checks: "ในแบบ"
    # ✅ ภงด.3: absolute (ล็อกแล้ว)
    if is_pnd3:
        _draw_check_in_box(c, *_xy_pnd3_abs(), box_size=14)

    # ✅ ภงด.53: absolute (ย้ายไปอีกจุดได้ด้วย CHK_PND53_DX/DY)
    if is_pnd53:
        _draw_check_in_box(c, *_xy_pnd53_abs(), box_size=14)

    # checks: ด้านล่าง "ผู้จ่ายเงิน (1) หัก ณ ที่จ่าย"
    _draw_check_in_box(c, *_xy("chk_paytype_1_box"), box_size=14)

    # date in table
    _draw_date_string(c, font, dt, *_xy("row_paydate_text"), size=12)

    # money (row)
    c.setFont(font, 12)
    c.drawRightString(POS["row_base_amt_right"] + OFFSET_X, POS["row_money_y"] + OFFSET_Y, _fmt_money(base_amount))
    c.drawRightString(POS["row_wht_amt_right"] + OFFSET_X, POS["row_money_y"] + OFFSET_Y, _fmt_money(wht_amount))

    # money (sum)
    c.drawRightString(POS["sum_base_amt_right"] + OFFSET_X, POS["sum_money_y"] + OFFSET_Y, _fmt_money(base_amount))
    c.drawRightString(POS["sum_wht_amt_right"] + OFFSET_X, POS["sum_money_y"] + OFFSET_Y, _fmt_money(wht_amount))

    # thai baht text
    _draw_text(c, font, *_xy("wht_text"), thai_baht_text(wht_amount), 12)

    # sign date (boxes)
    sx, sy = _xy("sign_date_start")
    _draw_date_ddmmyyyy_boxes(
        c, font, dt,
        sx, sy,
        POS["sign_date_box_w"], POS["sign_date_box_h"],
        size=12
    )

    c.showPage()
    c.save()
    overlay_buf.seek(0)

    # merge
    overlay_reader = PdfReader(overlay_buf)
    base_page.merge_page(overlay_reader.pages[0])

    writer = PdfWriter()
    writer.add_page(base_page)

    # กัน AcroForm เดิมกลับมาโผล่ในไฟล์ output
    try:
        writer._root_object[NameObject("/AcroForm")] = None
    except Exception:
        pass

    fd, out_path = tempfile.mkstemp(prefix=f"{getattr(doc, 'doc_no', 'WHT')}_", suffix=".pdf")
    os.close(fd)
    with open(out_path, "wb") as f:
        writer.write(f)

    return out_path
