# Contractor Project Tracker (PWA) — Flask + PostgreSQL

ระบบติดตาม “โครงการงานรับเหมา” แบบ PWA ใช้งานบนมือถือได้ (Install ได้) เน้น UI อ่านง่าย เหมาะกับผู้ใช้งานอายุเยอะ

## ฟีเจอร์หลัก
- รายการโครงการ + ค้นหา (ชื่อโครงการ / รหัสโครงการ)
- เพิ่ม/แก้ไขโครงการ **ในหน้าเดียว**
  - รายละเอียดโครงการ
  - รายการวัสดุ (ยี่ห้อ/แบรนด์, รหัส, ราคาต่อหน่วย, จำนวน)
  - ผู้รับเหมาช่วง (ว่าจ้างเท่าไหร่, หัก ณ ที่จ่ายเท่าไหร่, หมายเหตุ)
  - ค่าใช้จ่ายอื่น (หมวด, รายการ, จำนวนเงิน)
  - จำนวนวันทำงาน
- สถานะโครงการ: `กำลังทำ` / `กำลังเก็บ Defect` / `งานจบ`
- หน้าดashboard สรุปค่าใช้จ่ายรวม แยกตามหมวดหมู่

> หมายเหตุ: โครงสร้างนี้ทำให้คุณเริ่มใช้งานได้ทันที และต่อยอดเพิ่ม (ไฟล์แนบ, รูปภาพ, export excel, สิทธิ์ผู้ใช้, ฯลฯ) ได้ง่าย

---

## ติดตั้งและรัน (Local)

### 1) สร้าง virtualenv และติดตั้งไลบรารี

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2) ตั้งค่า PostgreSQL
สร้าง DB ชื่ออะไรก็ได้ (ตัวอย่าง `contract_pwa`) แล้วตั้งค่า `DATABASE_URL` ในไฟล์ `.env`

- Windows (PowerShell)
```powershell
copy .env.example .env
notepad .env
```

ตัวอย่าง `.env`:
```env
FLASK_ENV=development
SECRET_KEY=dev-secret-change-me
DATABASE_URL=postgresql://postgres:your_password@localhost:5432/contract_pwa
```

### 3) สร้างตารางฐานข้อมูล
```bash
flask --app wsgi.py db init
flask --app wsgi.py db migrate -m "init"
flask --app wsgi.py db upgrade
```

### 4) รัน
```bash
flask --app wsgi.py run --debug
```
เปิดที่: http://127.0.0.1:5000

---

## Deploy (แนวทาง)
- Render / Railway / Fly.io: ตั้งค่า `DATABASE_URL` เป็น PostgreSQL ของผู้ให้บริการ และ set `SECRET_KEY` ให้ปลอดภัย
- รัน migration ใน shell: `flask --app wsgi.py db upgrade`

---

## โครงสร้างโปรเจค
```
contract_pwa/
  app/
    blueprints/
      projects.py
      dashboard.py
    static/
      css/app.css
      js/app.js
      pwa/manifest.webmanifest
      pwa/service-worker.js
      icons/*
    templates/
      base.html
      projects_list.html
      project_form.html
      dashboard.html
  migrations/
  wsgi.py
  config.py
  requirements.txt
  .env.example
```
