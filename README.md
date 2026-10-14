# Project LUMA

LUMA เป็นเว็บแอปสร้างและแก้ไขภาพ จัดการบัญชี งาน และรายการโปรด ผ่าน Flask Backend และ FastAPI AI Engine

ปรับปรุงคู่มือวันที่ 14 ตุลาคม 2026 สำหรับโค้ดรวมบน `main` รวมขั้นตอนติดตั้ง ตั้งค่า เปิดบริการ และตรวจผล เพื่อให้ผู้ตรวจดาวน์โหลดไปรันตามได้ตามข้อกำหนดการส่งโครงงานข้อ 2

**ลิงก์โครงงาน:** https://github.com/Panussu/ProjectLUMA

เริ่มจาก [วิธีรันบน Windows](#เริ่มใช้งานบน-windows) หากไม่มี GPU ให้ใช้โหมดทดสอบในคู่มือนี้ ส่วน [เอกสารประกอบการส่ง](#เอกสารประกอบการส่งโครงงาน) มีรายงาน Word พร้อมภาพหลักฐาน

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

## Infrastructure: ระบบ Distributed System แบบ 3 PCs

โครงการนี้ใช้ **คอมพิวเตอร์ 3 เครื่อง** ตามแผนภาพต้นฉบับ แต่ละเครื่องมี IP Address แยกกันและเชื่อมต่อผ่านเครือข่าย LAN/VLAN ที่สื่อสารถึงกันได้ Frontend กับ Nginx อยู่เครื่องเดียวกัน และ Flask กับ SQLite อยู่เครื่องเดียวกัน IP ด้านล่างตรงกับแผนภาพและไฟล์ VLAN example; ตรวจ IP จริงก่อนเปิดบริการ ไม่ใช่หลักฐานว่าทดสอบเครือข่ายจริงแล้ว

![Distributed System ตามแผนภาพโครงการ](docs/images/infrastructure/distributed-system.png)

*ภาพที่ 1: Browser เข้า Nginx แล้วเรียก Frontend/Flask; Flask ติดต่อ AI Server และ SQLite*

### เครื่อง บริการ และ IP Address

| เครื่องตาม deployment ปัจจุบัน | IP ตามแผนภาพ | บริการและข้อมูล |
| --- | --- | --- |
| PC 2 — Frontend + Nginx | `192.168.1.10` | HTML, CSS, JavaScript, Bootstrap และ reverse proxy; Browser เข้า `http://192.168.1.10` |
| PC 3 — Flask + SQLite | `192.168.1.20` | Flask API port `5000`, authentication, jobs, logging, database และไฟล์ภาพ |
| PC 1 — AI Server | `192.168.1.30` | FastAPI port `8000` และ Forge บนเครื่องเดียวกันที่ `127.0.0.1:7860` |

หมายเลข PC ใช้ตามคู่มือ deployment ใน repository ไม่ใช่หมายเลขสมาชิกในตารางแบ่งหน้าที่

### ข้อมูลและ protocol ที่ใช้

แผนภาพระบุองค์ประกอบและ IP ส่วน ports/protocol ด้านล่างอ้างอิง configuration ที่ใช้อยู่ (`nginx/luma.conf` และไฟล์ `.env.vlan.example`):

| การเชื่อมต่อ | Protocol / ข้อมูล | รายละเอียด |
| --- | --- | --- |
| Browser → Nginx `.10:80` | HTTP บน TCP; HTML/CSS/JS, JSON และไฟล์ภาพ | Nginx ส่งหน้าเว็บและไฟล์ static; browser ใช้ origin เดียวกัน |
| Nginx → Flask `.20:5000` | HTTP reverse proxy | ส่ง `/api/` และ `/media/` ไป Flask พร้อม forwarded headers; user authentication ใช้ JWT |
| Flask → FastAPI `.30:8000` | HTTP API; JSON/ข้อมูลภาพตาม endpoint | ใช้ `X-LUMA-Service-Token` และ `X-LUMA-Job-ID` เพื่อเชื่อมบริการและระบุงาน |
| FastAPI → Forge `127.0.0.1:7860` | HTTP API; JSON และภาพ Base64 ตาม Forge contract | ใช้ `/sdapi/v1/txt2img` และ `/sdapi/v1/img2img`; Forge อยู่ภายใน PC 1 |
| Flask → SQLite บน `.20` | การอ่าน/เขียนไฟล์ผ่าน SQLite/SQLAlchemy | ฐานข้อมูลเริ่มต้น `backend/data/luma.db`; ไม่มี database TCP port หรือ SQLite server แยก |

Configuration VLAN ปัจจุบันเป็น HTTP ไม่ได้ตั้ง HTTPS/TLS ในไฟล์ตัวอย่าง SQLite ที่แสดง IP `.20` ในภาพหมายถึงฐานข้อมูลอยู่บนเครื่อง Backend ไม่ใช่บริการฐานข้อมูลที่เปิดให้เครื่องอื่นเชื่อมต่อโดยตรง

### ขั้นตอนการทำงาน

1. ผู้ใช้เปิด `http://192.168.1.10` ผ่าน Browser; Nginx ส่ง Frontend ให้แสดงหน้าเว็บ
2. ผู้ใช้ลงทะเบียน/เข้าสู่ระบบ Frontend ส่ง API ผ่าน Nginx ไป Flask ซึ่งตรวจข้อมูลกับ SQLite และออก JWT
3. ผู้ใช้ส่ง prompt หรือภาพสำหรับแก้ไข Flask ตรวจสิทธิ์และข้อมูล สร้าง job แล้วตอบ HTTP 202 พร้อมข้อมูลติดตามงาน
4. Flask เรียก FastAPI ที่ `192.168.1.30:8000`; FastAPI จัดคิวและเรียก Forge ภายในเครื่อง AI
5. Frontend ติดตามสถานะงานผ่าน Nginx/Flask ทุกประมาณ 1 วินาที โดยตรวจเจ้าของงานก่อนคืนข้อมูล
6. เมื่อได้ผล Flask จัดเก็บไฟล์ภาพและบันทึกข้อมูลใน SQLite; Browser เรียกภาพผ่าน `/media/` ซึ่ง Flask ตรวจ JWT หรือ signed URL ก่อนส่งภาพ
7. Favorites, history และการยกเลิกงานใช้ Backend ตรวจเจ้าของข้อมูลเช่นเดียวกัน Browser ไม่ติดต่อ Forge หรือ SQLite โดยตรง

### ตั้งค่าให้ตรงกับแผนภาพ

- PC 2: `nginx/luma.conf` ใช้ `server_name 192.168.1.10` และ upstream `192.168.1.20:5000`; แก้ frontend root ให้ตรงกับ path จริง
- PC 3: `backend/.env.vlan.example` กำหนด `AI_SERVICE_URL=http://192.168.1.30:8000` และ `CORS_ORIGINS=http://192.168.1.10`
- PC 1: `ai-engine/.env.vlan.example` กำหนด port `8000`, `AI_PROVIDER=forge` และ `FORGE_URL=http://127.0.0.1:7860`
- ตั้ง shared service token ให้ตรงกันบน PC 1/PC 3 และเปลี่ยน signing secrets ของ Backend เปิด firewall ให้ Nginx ติดต่อ Backend และ Backend ติดต่อ AI ได้ โดยไม่จำเป็นต้องเปิด Forge ให้ทุกเครื่อง

### การแบ่งหน้าที่ในทีม

![ตัวอย่างการแบ่งหน้าที่จากเอกสารต้นฉบับ](docs/images/infrastructure/team-roles.png)

*ภาพที่ 2: ตัวอย่างบทบาทสมาชิก ไม่ใช่การระบุชื่อผู้รับผิดชอบจริง*

| บทบาทตามแผนภาพ | สิ่งที่ส่งมอบ | Branch ที่เกี่ยวข้อง |
| --- | --- | --- |
| UX/UI Frontend | หน้าเว็บ, Bootstrap, JavaScript | `Frontend` |
| Flask Backend | Authentication, API, Database, Logging | `Backend` |
| AI Engineer | Image Generation/Editing, Model/LoRA, API tests, Queue | `AiEngine` |
| QA / DevOps | ทดสอบระบบ, คู่มือ, Deployment, Dashboard, Backup | `QA` |
| Reverse Proxy / Routing | Nginx, การส่งต่อคำขอและการเชื่อมเครือข่าย; ช่วยส่วนอื่นตามความเหมาะสม | `Routing` |

บทบาทเหล่านี้เป็นการแบ่งงานพัฒนา ไม่ได้หมายความว่าต้องใช้คอมพิวเตอร์หนึ่งเครื่องต่อสมาชิกหนึ่งคน

![ทางเลือกจำนวนเครื่องจากเอกสารต้นฉบับ](docs/images/infrastructure/deployment-options.png)

*ภาพที่ 3: โครงการนี้ใช้รูปฝั่งซ้าย — 3 เครื่องและ SQLite อยู่กับ Flask ส่วนรูปฝั่งขวาเป็นตัวอย่างทางเลือก 4 เครื่องที่แยก PostgreSQL ซึ่งไม่ได้ใช้ใน deployment นี้*

ดูขั้นตอนตรวจเครือข่ายและเปิดบริการใน [คู่มือระบบ 3 เครื่อง](docs/PROJECTLUMA_3PC_TEST_GUIDE.md)

## เริ่มใช้งานบน Windows

### 1 เตรียมเครื่องและดาวน์โหลดโปรเจกต์

ต้องมี Git และ Python 3.12 โดยคำสั่ง `python` ต้องเรียก Python รุ่นที่ติดตั้งไว้ ตรวจด้วยคำสั่งด้านล่าง Node.js 22 จำเป็นเฉพาะเมื่อต้องการรันชุดทดสอบ Frontend ส่วน Docker Desktop และ Forge ไม่จำเป็นสำหรับวิธีทดสอบด้วย CPU

```powershell
git --version
python --version
git clone https://github.com/Panussu/ProjectLUMA.git
Set-Location ProjectLUMA
```

ให้รันคำสั่งถัดไปจากโฟลเดอร์ `ProjectLUMA` ที่มี `README.md`, `backend`, `ai-engine` และ `scripts` หากดาวน์โหลด ZIP จาก GitHub ให้แตกไฟล์แล้วเปิด PowerShell ที่โฟลเดอร์นี้แทนการ clone

### 2 สร้างและแก้ไฟล์ตั้งค่า

คัดลอกไฟล์ตัวอย่างเฉพาะเมื่อยังไม่มี เพื่อรักษาค่าที่ตั้งไว้เดิม:

```powershell
if (-not (Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
if (-not (Test-Path ai-engine/.env)) { Copy-Item ai-engine/.env.example ai-engine/.env }
```

เปิดไฟล์ `backend/.env` และ `ai-engine/.env` ด้วยตัวแก้ไขข้อความ แล้วตั้งค่าตามตาราง ใช้คำสั่งนี้สร้างค่าสุ่ม 3 ครั้ง: ครั้งแรกใช้เป็นโทเคนร่วมทั้งสองบริการ อีกสองครั้งใช้เป็นกุญแจ Backend คนละค่า

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

| ไฟล์ | ค่า | สิ่งที่ต้องกำหนดสำหรับเครื่องเดียว |
| --- | --- | --- |
| `backend/.env` | `SECRET_KEY`, `JWT_SECRET_KEY` | ค่าสุ่มคนละค่า อย่างน้อย 32 ตัวอักษร |
| ทั้งสองไฟล์ | `AI_SERVICE_TOKEN` | ค่าสุ่มเดียวกันทั้ง Backend และ AI Engine |
| `backend/.env` | `AI_SERVICE_URL` | `http://127.0.0.1:8000` |
| `backend/.env` | `CORS_ORIGINS` | `http://localhost:8080` |
| `backend/.env` | `HOST`, `PORT` | `127.0.0.1`, `5000` |
| `ai-engine/.env` | `HOST`, `PORT` | `127.0.0.1`, `8000` |
| `ai-engine/.env` | `AI_PROVIDER` | `development-procedural` สำหรับทดสอบด้วย CPU |

ไม่ต้องสร้าง SQLite เอง ระบบเตรียมฐานข้อมูลเริ่มต้นใน `backend/data/luma.db` เมื่อเปิด Backend ห้ามนำ `.env` หรือค่าลับขึ้น GitHub

**โหมด CPU:** ใช้ `development-procedural` เพื่อตรวจการสมัครสมาชิก ส่งงาน รับภาพ และแก้ไขภาพพื้นฐาน ภาพมาจาก Pillow ไม่ใช่โมเดล Generative AI และความสามารถที่พึ่งพา Forge จะไม่เทียบเท่าโหมดจริง

**โหมดโมเดลจริง:** ตั้ง `AI_PROVIDER=forge`, เปิด Forge พร้อมโมเดลและ `--api --port 7860` แล้วตั้ง `FORGE_URL=http://127.0.0.1:7860` ใน `ai-engine/.env` แก้ `MODELS_DIR` และ `LORAS_DIR` ให้ตรงกับเครื่องของตนเอง หากใช้ API authentication ให้ตั้ง `FORGE_USERNAME` และ `FORGE_PASSWORD` ด้วย ดู [คู่มือ AI Engine](ai-engine/README.md)

### 3 เปิดบริการตามลำดับ

เปิด PowerShell 3 หน้าต่าง โดยแต่ละหน้าต่างอยู่ที่โฟลเดอร์โครงงานเดียวกัน และปล่อยหน้าต่างบริการไว้ระหว่างใช้งาน

**หน้าต่างที่ 1 เปิด AI Engine**

```powershell
./scripts/run-ai.ps1
```

รอจนบริการพร้อม แล้วเปิด `http://127.0.0.1:8000/health` หรือ `http://127.0.0.1:8000/docs` ได้ก่อนเริ่ม Backend หากใช้ Forge ต้องเปิด Forge ก่อนขั้นตอนนี้

**หน้าต่างที่ 2 เปิด Backend**

```powershell
./scripts/run-backend.ps1
```

รอให้เปิด `http://127.0.0.1:5000/api/v1/health` ได้ แล้วจึงเปิด Frontend

**หน้าต่างที่ 3 เปิด Frontend**

```powershell
./scripts/run-frontend.ps1
```

สคริปต์ AI/Backend จะสร้าง `.venv` แยกภายในแต่ละบริการและติดตั้ง dependencies ครั้งแรกต้องใช้อินเทอร์เน็ตและอาจใช้เวลานาน จากนั้นเปิด **http://localhost:8080** ในเบราว์เซอร์ ไม่เปิด `frontend/index.html` ด้วยการดับเบิลคลิกไฟล์

### 4 ตรวจว่ารันได้และทดลองใช้งาน

จาก PowerShell อีกหน้าต่าง ตรวจทั้งสามบริการ:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:5000/api/v1/health
(Invoke-WebRequest http://localhost:8080 -UseBasicParsing).StatusCode
```

สองคำสั่งแรกควรได้ข้อมูล JSON โดยไม่เกิดข้อผิดพลาดการเชื่อมต่อ และคำสั่งสุดท้ายควรได้ `200` จากนั้นตรวจตามลำดับ:

1. เปิดเว็บ กด **Sign in** และสมัครบัญชีใหม่ในหน้าต่างบัญชี แล้วเข้าสู่ระบบ
2. ที่แท็บ **Generate** กรอก prompt เช่น `A red apple on a white table` ใช้ขนาด 512 × 512 และ steps 20 แล้วส่งงาน
3. รอจนงานเป็น `completed` ตรวจว่ามีภาพผลลัพธ์และดาวน์โหลดภาพได้ หากเป็น `failed` ให้อ่านข้อความผิดพลาดและหน้าต่างบริการ
4. ที่แท็บ **Edit image** เลือกภาพทดสอบ กรอกคำสั่งแก้ไข ส่งงาน และตรวจผลลัพธ์
5. ทดลองดูประวัติงาน ออกจากระบบ และเข้าสู่ระบบใหม่เพื่อตรวจว่างานยังเป็นของบัญชีเดิม

รายการข้างต้นเป็นเกณฑ์ตรวจหลังติดตั้ง ไม่ใช่การยืนยันว่าได้รัน Forge หรือเครือข่ายจริงของผู้อ่านแล้ว โหมด CPU เหมาะกับตรวจวงจรงาน ส่วนคุณภาพภาพจากโมเดลต้องตรวจในโหมด Forge

### 5 หยุดบริการและแก้ปัญหาที่พบบ่อย

กด `Ctrl+C` ในแต่ละหน้าต่างเพื่อหยุดบริการ การปิดหน้าต่าง Frontend อย่างเดียวไม่ได้หยุด Backend หรือ AI Engine

| อาการ | ตรวจและแก้ไข |
| --- | --- |
| ไม่พบ `python` หรือ `git` | ตรวจการติดตั้งและ PATH แล้วเปิด PowerShell ใหม่ |
| รันไฟล์ `.ps1` ไม่ได้ | ใช้วิธีรันด้วย Python ด้านล่าง โดยไม่ต้องเปลี่ยนนโยบาย PowerShell |
| พอร์ต 5000, 8000 หรือ 8080 ถูกใช้ | ปิดบริการเดิมที่ตนเปิดไว้ หรือปรับพอร์ตและ URL ที่เกี่ยวข้องให้ตรงกัน |
| หน้าเว็บแสดง Offline | ตรวจ Backend `/api/v1/health` และ AI `/health` แล้วดูข้อความในหน้าต่างบริการ |
| AI ตอบ Unauthorized หรือ HTTP 401 | ตรวจ `AI_SERVICE_TOKEN` ให้ตรงกันทั้งสองไฟล์ แล้วเริ่มบริการใหม่ |
| ใช้ signed media ไม่ได้ | เปลี่ยนกุญแจตัวอย่างเป็นค่าสุ่มจริงและเริ่ม Backend ใหม่ |
| เรียก Forge ไม่ได้หรือได้ HTTP 502 | เปิด Forge พร้อม `--api` ตรวจ `FORGE_URL`, โมเดล และ API authentication หรือเลือกโหมด CPU เพื่อแยกทดสอบ |
| เปิดผ่าน IP แล้ว API/CORS ไม่ผ่าน | วิธีเครื่องเดียวนี้ใช้ `http://localhost:8080`; หากเปลี่ยน origin ให้ตั้ง `CORS_ORIGINS` และ API address ให้ตรงกัน หรือใช้ Nginx ตามคู่มือสามเครื่อง |

**วิธีรันโดยไม่ใช้สคริปต์ PowerShell:** จาก root เตรียม environment และ dependencies ครั้งเดียว:

```powershell
python -m venv ai-engine/.venv
python -m venv backend/.venv
./ai-engine/.venv/Scripts/python.exe -m pip install -r ai-engine/requirements.txt
./backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
```

หลังตั้ง `.env` ตามขั้นตอน 2 แล้ว เปิดคนละหน้าต่างเช่นเดิม:

```powershell
# หน้าต่างที่ 1 เริ่มจาก root
Set-Location ai-engine
./.venv/Scripts/python.exe app.py
```

```powershell
# หน้าต่างที่ 2 เริ่มจาก root
Set-Location backend
./.venv/Scripts/python.exe run.py
```

```powershell
# หน้าต่างที่ 3 อยู่ที่ root
python -m http.server 8080 --directory frontend
```

สำหรับระบบสามเครื่อง Nginx จะส่ง `/api/v1` บน origin เดียวกับหน้าเว็บ ใช้ [คู่มือสามเครื่อง](docs/PROJECTLUMA_3PC_TEST_GUIDE.md) และ [คู่มือ Deployment](docs/DEPLOYMENT.md) แทนค่าของวิธีเครื่องเดียว

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

## วิธีรันทดสอบและผลตรวจที่บันทึกไว้

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
| Python ตามบันทึกตรวจ revision `5b52b9e` | 109 ผ่าน |
| Frontend Node ตามบันทึกตรวจ revision `5b52b9e` | 15 ผ่าน |
| HTTP/API ตาม audit ล่าสุด | 78 ผ่าน |
| Chromium ตาม audit ล่าสุด | 53 ผ่าน |

ดู [latest audit](docs/WEBAPP_AUDIT_2026-10-14.md) ตารางนี้เก็บผลที่บันทึกไว้ก่อนเพิ่มเอกสารส่งโครงงาน ไม่ได้รันชุดทดสอบแอปซ้ำในการปรับ README รอบนี้ การทดสอบดังกล่าวใช้ procedural provider และ fixtures ยังไม่ได้ยืนยัน real Forge/GPU, container build/runtime หรือสามเครื่องจริง

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

## เอกสารประกอบการส่งโครงงาน

- [รายงาน Word ภาษาไทยพร้อมภาพหลักฐาน](docs/reports/LUMA_Visible_Bug_Report_TH.docx) — 23 หน้า ภาพประกอบ 12 ภาพ พร้อมขั้นตอนทำซ้ำ ผลที่พบ และแนวทางแก้ไข
- [สรุปขอบเขตรายงาน](docs/reports/README.md) — อ่านเพื่อแยกเว็บที่ถูกตรวจออกจากโปรเจกต์นี้
- [ผลตรวจ ProjectLUMA](docs/WEBAPP_AUDIT_2026-10-14.md) และ [คู่มือรันระบบสามเครื่อง](docs/PROJECTLUMA_3PC_TEST_GUIDE.md)

รายงาน Word เป็นการตรวจเว็บภายนอก `boss2912/luma-webapp-g04` เมื่อวันที่ 14 ตุลาคม 2026 ประเด็นในเอกสารจึงไม่ใช่ผลยืนยันข้อผิดพลาดของ `Panussu/ProjectLUMA` มีประเด็นยืนยันจากหน้าจอ 7 รายการและข้อเสนอแนะ 1 รายการ โดยเหตุการณ์ 502 พบชั่วคราวหนึ่งครั้ง
