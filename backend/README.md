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

## การเชื่อมต่อ AiEngine

กำหนด `AI_SERVICE_URL` ให้ชี้ FastAPI บน PC 1 และ `AI_SERVICE_TOKEN` ให้ตรงกันทั้งสองเครื่อง Backend ส่งโทเคนผ่าน `X-LUMA-Service-Token` โดยอัตโนมัติ งานสร้างภาพส่ง JSON ไป `/v1/generate` และงานแก้ไขภาพส่ง multipart ไป `/v1/edit` ภาพ PNG ที่ตอบกลับจะถูกตรวจและเก็บใน `MEDIA_ROOT`

`AI_READ_TIMEOUT` เริ่มต้น 600 วินาที เพื่อครอบคลุมการรอคิวของ AiEngine (ค่าเริ่มต้น 180 วินาที) และการรอ Forge สร้างภาพ (ค่าเริ่มต้น 300 วินาที) ปรับค่านี้ให้สูงกว่าผลรวมของสองช่วงเมื่อเปลี่ยนการตั้งค่าคิวหรือ Forge ส่วน `AI_METADATA_TIMEOUT` เริ่มต้น 10 วินาที ใช้กับรายการตัวเลือกและภาพพรีวิว

ส่งตัวเลือกเพิ่มเติมใน `POST /api/v1/jobs/generate` ได้ เช่น

```json
{
  "prompt": "a paper city in daylight",
  "model": "checkpoint-xl",
  "loras": [{"name": "detail", "weight": 0.7}],
  "sampler": "Euler a",
  "scheduler": "Karras",
  "cfg_scale": 7.5,
  "clip_skip": 2,
  "style_preset": "anime_illustrious"
}
```

`POST /api/v1/jobs/edit` รับฟิลด์เดียวกันใน multipart form โดย `loras` ต้องเป็นข้อความ JSON array เช่น `[{"name":"detail","weight":0.7}]` Backend เก็บค่าที่ขอใน `job.ai_options` และค่าที่ AiEngine รายงานกลับใน `job.ai_result` งานเก่าจะมีสองช่องนี้เป็น `{}` ฐานข้อมูล SQLite เดิมใช้ต่อได้เพราะข้อมูลตัวเลือกอยู่ในตารางใหม่ `job_ai_options`

ผู้ใช้ที่มี JWT เรียก `GET /api/v1/ai/models`, `/loras`, `/samplers`, `/schedulers`, `/settings`, `/styles`, `/styles/<style_id>` และ `/queue/status` เพื่อดูตัวเลือกจาก AiEngine ได้ รายการโมเดลและ LoRA ที่มีพรีวิวจะได้ `preview_url` ของ Backend ซึ่งเป็นลิงก์ลงลายเซ็นและหมดอายุตาม `MEDIA_TOKEN_MAX_AGE` จึงใช้เป็น `src` ของภาพในเบราว์เซอร์ได้โดยไม่เปิดโทเคนบริการให้ Frontend

สถานะงานยังอ่านจาก `GET /api/v1/jobs/<job_id>` ค่า `progress` ของ Backend แสดงช่วง queued, processing และ completed เท่านั้น เนื่องจาก `/v1/progress` ของ AiEngine เป็นสถานะรวมของ GPU และไม่มี job ID จึงไม่สามารถผูกเปอร์เซ็นต์หรือภาพระหว่างทางกับงานของผู้ใช้แต่ละคนได้อย่างปลอดภัย

## ความสามารถเพิ่มเติมในสาขา Backend

ดาวน์โหลดภาพได้ด้วยลิงก์ที่มีลายเซ็นและอายุจำกัด หรือส่วนหัว `Authorization: Bearer <token>` ของเจ้าของภาพ โทเคนของบัญชีอื่นไม่ได้ให้สิทธิ์อ่านภาพนั้น

worker ตรวจว่า AI ส่ง PNG ที่อ่านได้และมีพิกเซลไม่เกิน `MAX_OUTPUT_PIXELS` แล้วเขียนผ่านไฟล์ชั่วคราวก่อนแทนที่ปลายทาง หากภาพเสีย งานจะล้มเหลวโดยไม่เผยแพร่ไฟล์ผลลัพธ์ที่ใช้ไม่ได้

`DEPLOYMENT_MODE=vlan` เปิดการตรวจค่าตอนเริ่มบริการ เปลี่ยนความลับตัวอย่างเป็นค่าสุ่มยาวอย่างน้อย 32 ตัวอักษร โดยกุญแจ Backend กับ JWT ต้องต่างกัน ส่วนโทเคนบริการต้องตรงกับ PC 1 ใช้ `FLASK_DEBUG=0` ระบุ origin ของ Frontend และให้ `AI_SERVICE_URL` ชี้ไปยังเครื่อง AI จริง ระบบจะปฏิเสธการเริ่มหากค่าไม่ผ่านเงื่อนไข

เมื่อเริ่มใหม่ ระบบนำงาน `queued` กลับเข้าคิว และเปลี่ยนงาน `processing` ที่ถูกขัดจังหวะเป็น `failed` เพื่อให้ผู้ใช้ส่งใหม่ ใช้ `RECOVER_JOBS_ON_STARTUP=1` สำหรับสาธิต เว้นแต่กำลังเปิดฐานข้อมูลเพื่อบำรุงรักษาโดยไม่ต้องการเริ่มงาน

## สำรองข้อมูลและล้างงานเก่า

หยุดส่งงานใหม่และรอให้งานที่กำลังทำจบก่อนสำรอง จากโฟลเดอร์ backend ให้รัน

```powershell
./.venv/Scripts/python.exe maintenance.py backup
```

ระบบเก็บสำเนา SQLite ภาพผลลัพธ์ และ manifest ในโฟลเดอร์แยกตามเวลาภายใต้ `backend/backups` ต้องเก็บโฟลเดอร์นี้เป็นส่วนตัวและอย่ากำหนดปลายทางไว้ใน media การสำรองไม่รวมภาพต้นทางที่รอแก้ไข

ตรวจรายการงาน completed หรือ failed ที่หมดอายุการเก็บก่อน แล้วจึงใช้ `--apply` เมื่อต้องการลบระเบียนและไฟล์จริง

```powershell
./.venv/Scripts/python.exe maintenance.py cleanup
./.venv/Scripts/python.exe maintenance.py cleanup --apply
```

จำนวนวันเริ่มต้นกำหนดด้วย `MEDIA_RETENTION_DAYS` ตรวจสำเนาสำรองก่อนลบ และทดสอบกู้ทั้งฐานข้อมูลกับไฟล์ที่อ้างถึง

