# app/utils/__init__.py
from __future__ import annotations

def thai_baht_text(amount):
    """
    Placeholder helper: คืนข้อความเป็นสตริง
    (เอาไว้ให้แอพไม่พังตอน import)
    คุณสามารถมาเปลี่ยนเป็นเวอร์ชันแปลง 'จำนวนเงิน -> คำอ่านเงินบาท' ภายหลังได้
    """
    try:
        return f"{amount}"
    except Exception:
        return ""
