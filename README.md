# ProjectLUMA Frontend

สาขานี้ดูแลหน้าเว็บ HTML/CSS/JavaScript ที่ให้บริการบน PC 2 ผ่าน Nginx มีฟอร์มสมัครสมาชิก เข้าสู่ระบบ สร้างภาพ แก้ไขภาพ ติดตามสถานะ และประวัติงาน คอมเมนต์ภาษาไทยอธิบายส่วนของหน้าเว็บ รูปแบบ CSS และฟังก์ชัน JavaScript

## ทดสอบหน้าเว็บ

เปิด PowerShell ที่โฟลเดอร์คลังโค้ดแล้วรัน

```powershell
python -m http.server 8080 --directory frontend
```

เปิด `http://localhost:8080` โหมดนี้เรียก API ที่ `http://localhost:5000/api/v1` จึงต้องมี Backend ทำงานในเครื่องเดียวกัน หรือกำหนด `window.LUMA_API_BASE` ก่อนโหลด app.js พร้อมตั้ง CORS ฝั่ง Backend ให้ตรงกัน

## การทำงานร่วมกับทีม

เมื่อติดตั้งจริง หน้าเว็บใช้ `/api/v1` และ `/media/` ผ่าน Nginx บน PC 2 ร่วมกับ Flask บน PC 3 และ FastAPI กับ Forge บน PC 1 ใน VLAN เดียวกัน โทเคนบริการ AI ต้องอยู่ฝั่งเซิร์ฟเวอร์ ไม่ฝังใน JavaScript

สาขานี้มีเฉพาะไฟล์ Frontend ใช้สาขา `main` สำหรับระบบครบชุด ตรวจ JavaScript ด้วย `node --check frontend/assets/app.js`
