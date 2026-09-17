# LUMA Backend

บริการ Flask บน PC 3 ดูแลการยืนยันตัวตน ผู้ใช้ งาน ฐานข้อมูล การเรียก AI ภายใน และไฟล์ภาพผลลัพธ์

## เริ่มพัฒนา

เปิด PowerShell ในโฟลเดอร์ `backend` แล้วรันคำสั่งต่อไปนี้ คัดลอกไฟล์ตัวอย่างเฉพาะเมื่อยังไม่มี `.env`

```powershell
python -m venv .venv
./.venv/Scripts/pip.exe install -r requirements.txt
Copy-Item .env.example .env
./.venv/Scripts/python.exe run.py
```

ตั้ง `AI_SERVICE_TOKEN` ให้ตรงกับ AI และกำหนด `SECRET_KEY` กับ `JWT_SECRET_KEY` เป็นค่าสุ่มคนละค่า SQLite ถูกสร้างใน `backend/data` หากใช้ PostgreSQL ต้องกำหนด `DATABASE_URL` และเตรียมฐานข้อมูลกับไดรเวอร์ให้พร้อม

## PC 3 ใน VLAN ห้องเรียน

PC 3 เก็บ SQLite ภาพต้นทางชั่วคราว และภาพผลลัพธ์ หากยังไม่มีค่ากำหนด ให้เริ่มจากตัวอย่าง VLAN แล้วแก้ IP และความลับก่อนเปิดบริการ

```powershell
Copy-Item .env.vlan.example .env
./.venv/Scripts/python.exe run.py
```

ตรวจทุกเครื่องด้วย `ipconfig` ตัวอย่างใช้ Nginx ที่ `192.168.1.10`, Flask ที่ `192.168.1.20:5000` และ FastAPI ที่ `192.168.1.30:8000` โทเคน `AI_SERVICE_TOKEN` ต้องตรงกับ PC 1 และอนุญาต TCP 5000 จาก PC 2

คิวงานใช้ thread pool ภายในโปรเซส ให้ใช้ Backend 1 โปรเซสในการสาธิต หากต้องเปิดหลายโปรเซสต้องออกแบบคิวร่วม เช่น Celery หรือ RQ พร้อมทดสอบเพิ่มเติม

