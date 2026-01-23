from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP

THAI_DIGITS = ["ศูนย์","หนึ่ง","สอง","สาม","สี่","ห้า","หก","เจ็ด","แปด","เก้า"]
THAI_POS = ["","สิบ","ร้อย","พัน","หมื่น","แสน"]
THAI_MILLION = "ล้าน"

def _chunk_to_thai(chunk: int) -> str:
    # 0..999999
    if chunk == 0:
        return ""
    parts = []
    digits = [int(d) for d in f"{chunk:06d}"]  # แสน หมื่น พัน ร้อย สิบ หน่วย
    for i, d in enumerate(digits):
        pos_from_right = 5 - i
        if d == 0:
            continue

        if pos_from_right == 1:  # สิบ
            if d == 1:
                parts.append("สิบ")
            elif d == 2:
                parts.append("ยี่สิบ")
            else:
                parts.append(f"{THAI_DIGITS[d]}สิบ")
        elif pos_from_right == 0:  # หน่วย
            # "เอ็ด" เมื่อมีหลักอื่นนำหน้า และหน่วยเป็น 1
            if d == 1 and chunk % 100 != 0 and chunk != 1:
                parts.append("เอ็ด")
            else:
                parts.append(THAI_DIGITS[d])
        else:
            parts.append(f"{THAI_DIGITS[d]}{THAI_POS[pos_from_right]}")
    return "".join(parts)

def _int_to_thai(n: int) -> str:
    if n == 0:
        return THAI_DIGITS[0]

    groups = []
    while n > 0:
        groups.append(n % 1_000_000)
        n //= 1_000_000

    out = []
    for i in range(len(groups) - 1, -1, -1):
        g = groups[i]
        if g == 0:
            continue
        out.append(_chunk_to_thai(g))
        if i > 0:
            out.append(THAI_MILLION)
    return "".join(out) if out else THAI_DIGITS[0]

def thai_baht_text(amount) -> str:
    d = Decimal(str(amount or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    prefix = "ลบ" if d < 0 else ""
    if d < 0:
        d = abs(d)

    baht = int(d)
    satang = int((d - Decimal(baht)) * 100)

    baht_text = _int_to_thai(baht) + "บาท"
    if satang == 0:
        return prefix + baht_text + "ถ้วน"
    return prefix + baht_text + _int_to_thai(satang) + "สตางค์ถ้วน"
