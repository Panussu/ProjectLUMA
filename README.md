# Project LUMA

LUMA เป็นเว็บแอปสร้างและแก้ไขภาพ จัดการบัญชี งาน และรายการโปรด ผ่าน Flask Backend และ FastAPI AI Engine

ปรับปรุงวันที่ 14 ตุลาคม 2026 อ้างอิง `main` ที่ `5b52b9e` ซึ่งรวม PR #2 และการแก้ไขความปลอดภัย session การตรวจสอบข้อมูล และการเปิดบริการล่าสุดแล้ว

## ความสามารถและสถาปัตยกรรม

Browser → Frontend/Nginx → Flask Backend → FastAPI AI Engine → Forge

| บริการ | หน้าที่ | พอร์ตทั่วไป |
| --- | --- | --- |
| Frontend/Nginx | หน้าเว็บและ same-origin proxy | 80; static development 8080 |
| Backend | JWT ผู้ใช้ งาน SQLite และไฟล์ส่วนตัว | 5000 |
| AI Engine | ตรวจสอบคำขอ คิว และ provider | 8000 |
| Forge | ประมวลผลโมเดลบนเครื่อง AI | 7860 |

- สร้าง/แก้ไขภาพ เลือกโมเดลและ LoRA ใช้ trigger words, tags, PNG metadata, filters และ upscaling ตาม provider
- ติดตามงานทุกประมาณ 1 วินาที ยกเลิกงานของตนเอง และเพิ่ม/ค้นหา/แก้ไข/ลบรายการโปรด
- แยกงานและผลลัพธ์ตามผู้ใช้ ป้องกันคำตอบจาก session เก่า และล้างข้อมูลส่วนตัวเมื่อออกจากระบบ
- ตรวจสอบตัวเลือก จำกัดขนาดและการประมวลผลภาพ และติดตามงานต่อเมื่อบริการขัดข้องชั่วคราว
- เก็บ Bootstrap 5.3.3 ใน repository เพื่อให้หน้าเข้าสู่ระบบทำงานได้เมื่อเข้าถึง CDN ไม่ได้
- รองรับ signed media URLs, backup/restore และ startup recovery

`development-procedural` ใช้ Pillow และ CPU สำหรับทดสอบระบบ ไม่ใช่โมเดลสร้างภาพที่ผ่านการฝึก Backend ใช้คิวใน process จึงควรเปิดหนึ่ง process จนกว่าจะใช้ shared queue ส่วน Forge ถูกจำกัดให้ทำงานทีละงาน เพราะ progress/interrupt ใช้สถานะร่วมกัน หลีกเลี่ยงการสร้างภาพผ่านหน้า Forge พร้อมกับ LUMA

## เริ่มใช้งานบน Windows

ต้องมี Python; Node.js ใช้ตรวจ frontend และ Docker ใช้กับ Compose CI ใช้ Python 3.12 และ Node.js 22

จาก root สร้างไฟล์ตั้งค่าเฉพาะเมื่อยังไม่มี:

```powershell
if (-not (Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
if (-not (Test-Path ai-engine/.env)) { Copy-Item ai-engine/.env.example ai-engine/.env }
```

ก่อนเปิดบริการ ตั้ง `AI_SERVICE_TOKEN` เป็นค่าสุ่มเดียวกันทั้งสองบริการ และตั้ง Backend `SECRET_KEY` / `JWT_SECRET_KEY` เป็นค่าสุ่มแยกกันอย่างน้อย 32 ตัวอักษร ค่า example ถูกปฏิเสธสำหรับ private signed media หากไม่มี Forge ตั้ง `AI_PROVIDER=development-procedural` ใน `ai-engine/.env` เพราะ native example ใช้ Forge

เปิดแต่ละคำสั่งใน PowerShell คนละหน้าต่าง:

```powershell
./scripts/run-ai.ps1
./scripts/run-backend.ps1
./scripts/run-frontend.ps1
```

สคริปต์ AI/Backend สร้าง virtual environment และติดตั้ง dependencies เปิด `http://localhost:8080` ซึ่งเรียก `http://127.0.0.1:5000/api/v1` ตรวจ `AI_SERVICE_URL=http://127.0.0.1:8000` และ `CORS_ORIGINS=http://localhost:8080` หากใช้ origin/hostname อื่นต้องตั้ง API address และ CORS ให้ตรงกัน Nginx ใช้ `/api/v1` บน origin เดียวกับหน้าเว็บ

## ตั้งค่าและ API

| ค่า | รายละเอียด |
| --- | --- |
| `AI_SERVICE_TOKEN` | shared service credential แยกจาก JWT ผู้ใช้ |
| `DATABASE_URL` | เริ่มต้น SQLite ที่ `backend/data/luma.db` |
| `MEDIA_ROOT` / `UPLOAD_ROOT` | `backend/media` / `backend/data/uploads` |
| `MAX_CONTENT_LENGTH` | เริ่มต้น 16 MiB |
| `MEDIA_TOKEN_MAX_AGE` | เริ่มต้น 3600 วินาที |
| `RECOVER_JOBS_ON_STARTUP` | native ปิด; production Compose เปิด |
| `DEPLOYMENT_MODE` | `vlan`/`production` ตรวจ configuration เพิ่มเติม |

การสร้างภาพรับ width/height 256–1024 หารด้วย 64 ลงตัว และ steps 1–50 การแก้ไขภาพตรวจสอบตัวเลือกและจำกัดการประมวลผลด้วย อย่า commit `.env` หรือ credentials

Backend prefix คือ `/api/v1`: `health`, `register`, `login`, `me`, `generate`, `edit`, `jobs`, `interrupt`, `skip` และ `prompts/favorites` งานสร้าง/แก้ไขตอบ HTTP 202; สถานะและการควบคุมงานตรวจเจ้าของ ผลลัพธ์ส่วนตัวต้องใช้ JWT เจ้าของหรือ signed URL ที่ถูกต้อง Backend ส่ง `X-LUMA-Service-Token` และ `X-LUMA-Job-ID` ไป AI Engine แต่ละ catalog/utility endpoint มีข้อกำหนด authentication ต่างกัน ดู [API contract](docs/API_CONTRACT.md) และ AI OpenAPI ที่ `http://127.0.0.1:8000/docs`

## Docker และสามเครื่อง

```powershell
docker compose up --build
```

Development Compose ใช้ procedural provider โดยค่าเริ่มต้น เปิด `http://localhost` สำหรับ production ตั้ง secrets จริงใน environment หรือ root `.env` แล้วรัน:

```powershell
docker compose -f docker-compose.prod.yml config --quiet
docker compose -f docker-compose.prod.yml up --build -d
```

Production persist database/media/uploads และเปิด recovery หากใช้ Forge ตั้ง `AI_PROVIDER=forge`, `FORGE_URL` และ credentials ตามจำเป็น URL เริ่มต้นคือ `http://host.docker.internal:7860`; ตรวจการเชื่อมต่อจาก container และ mount โฟลเดอร์โมเดล/LoRA เมื่อต้องอ่านไฟล์ host

ระบบสามเครื่องใช้ PC 1 AI, PC 2 Nginx, PC 3 Backend ตรวจ IP จริงแล้วแก้ environment/Nginx/firewall ตาม [คู่มือสามเครื่อง](docs/PROJECTLUMA_3PC_TEST_GUIDE.md) ใช้ `0.0.0.0` เป็น listen address เท่านั้น

## ผลทดสอบล่าสุด

รันจาก root:

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
./.venv/Scripts/python.exe -m pytest -q --tb=short
node --test tests/test_frontend.cjs
```

`./scripts/run-all-tests.ps1` ตรวจ Python, JavaScript syntax, frontend และ Compose พร้อม failing exit code สคริปต์เลือก `backend/.venv` ก่อน Python ใน PATH; หากใช้ environment นี้ต้องติดตั้ง `requirements-dev.txt` ด้วย interpreter เดียวกัน

| การตรวจสอบ | ผล |
| --- | --- |
| Python รันซ้ำสำหรับ README ครั้งนี้ | 109 ผ่าน |
| Frontend Node รันซ้ำครั้งนี้ | 15 ผ่าน |
| HTTP/API ตาม audit ล่าสุด | 78 ผ่าน |
| Chromium ตาม audit ล่าสุด | 53 ผ่าน |

ดู [latest audit](docs/WEBAPP_AUDIT_2026-10-14.md) การทดสอบใช้ procedural provider และ fixtures ยังไม่ได้ยืนยัน real Forge/GPU, container build/runtime หรือสามเครื่องจริง HTTP/browser เป็นผลจาก audit ไม่ได้รันซ้ำในการแก้ README ครั้งนี้

## Backup และเอกสาร

```powershell
./scripts/backup.ps1 -BackupDir backups -RetentionDays 7
./scripts/restore.ps1
./scripts/cleanup-backend.ps1 -Days 30
```

Restore เลือก ZIP ล่าสุดและขอยืนยัน หยุด Backend ทุก process ก่อนกู้คืน ระบบตรวจ archive paths และ SQLite integrity Cleanup แสดงรายการจนเพิ่ม `-Apply` ZIP workflow รองรับ SQLite; directory backup จาก `backup-backend.ps1` เป็นอีก workflow ไม่ใช่ input ของ ZIP restore

- [Backend README](backend/README.md), [AI README](ai-engine/README.md)
- [User guide](docs/USER_GUIDE.md), [deployment](docs/DEPLOYMENT.md), [architecture](docs/ARCHITECTURE.md)
- [QA suite](docs/QA_TEST_SUITE_GUIDE.md), [latest audit](docs/WEBAPP_AUDIT_2026-10-14.md)
- [Previous QA](docs/QA_TEST_REPORT.md) และ [previous fixes](docs/COMPARISON_AND_FIXES_2026-10-14.md) เป็นข้อมูล revision ก่อนหน้า จำนวนทดสอบจึงต่างจากล่าสุด
- [Overview site](project-overview-site/index.html), [code deep dive](project-overview-site/code-deep-dive.html)

พัฒนาแยกบน `Frontend`, `Backend`, `AiEngine`, `Routing`, `QA` แล้วรวมผ่าน review branch/PR ก่อนเข้า `main`
