# Project LUMA

LUMA (Learning-based Universal Media Artist) เป็นเว็บแอปพลิเคชันสำหรับสร้างภาพจากข้อความและแก้ไขภาพผ่านบริการ AI ระบบสาธิตใช้คอมพิวเตอร์ 3 เครื่องใน VLAN เดียวกัน ผู้ใช้สั่งงานและติดตามผลผ่านเบราว์เซอร์

## สถาปัตยกรรม

| เครื่อง | IP ตัวอย่าง | หน้าที่ |
| --- | --- | --- |
| PC 1 ฝั่ง AI | `192.168.1.30` | FastAPI รับคำขอจาก Flask แล้วเรียก WebUI Forge บนเครื่องเดียวกัน |
| PC 2 ฝั่งหน้าเว็บ | `192.168.1.10` | Nginx ให้บริการ HTML/CSS/JavaScript และส่งต่อคำขอ API กับภาพ |
| PC 3 ฝั่ง Backend | `192.168.1.20` | Flask จัดการผู้ใช้ JWT คิวงาน ไฟล์ภาพ และ SQLite |

IP และพอร์ตปรับได้ตามเครือข่ายจริง ตรวจด้วย `ipconfig` ก่อนใช้ สำหรับพัฒนาในเครื่องเดียวให้เปิดทุกบริการบนเครื่องเดียวได้

ผู้ใช้ → Nginx พอร์ต 80 → Flask พอร์ต 5000 → FastAPI พอร์ต 8000 → Forge พอร์ต 7860

Flask ดูแลบัญชีและวงจรชีวิตงาน ส่วน FastAPI แปลงคำขอให้ Forge ประมวลผลโมเดล เมื่อได้ภาพ Flask จะเก็บไฟล์แล้วส่งลิงก์ให้เบราว์เซอร์โหลดผ่าน Nginx

SQLite เป็นฐานข้อมูลเริ่มต้นเพราะไม่ต้องมีเครื่องแยก หากเปลี่ยนเป็น PostgreSQL ต้องกำหนด `DATABASE_URL` ติดตั้งไดรเวอร์ที่เกี่ยวข้อง และเตรียมฐานข้อมูลให้พร้อม

## โครงสร้างคลังโค้ด

| โฟลเดอร์ | เนื้อหา |
| --- | --- |
| `frontend/` | หน้าเว็บ การส่งคำขอ การเข้าสู่ระบบ และแสดงภาพ |
| `backend/` | Flask การยืนยันตัวตน ฐานข้อมูล และคิวงาน |
| `ai-engine/` | FastAPI เชื่อม Forge และ provider สำหรับทดสอบ |
| `nginx/` | การให้บริการไฟล์และเส้นทาง reverse proxy |
| `docs/` | สถาปัตยกรรม สัญญา API การติดตั้ง และแผนทดสอบ |
| `scripts/` | PowerShell สำหรับเริ่มบริการและตรวจเครือข่าย |
| `tests/` | กรณีทดสอบ API และบริการจำลอง |

คอมเมนต์ภาษาไทยในโค้ดอธิบายหน้าที่ของแต่ละส่วน ชื่อฟังก์ชัน ตัวแปร และเส้นทางยังตรงกับโปรแกรมเพื่อให้ค้นหาและพัฒนาร่วมกันได้

## สัญญา API

เมื่อติดตั้งผ่าน Nginx เบราว์เซอร์เรียก `/api/v1` บน origin เดียวกับเว็บไซต์ แล้ว Nginx ส่งต่อไปยัง Flask กรณีพัฒนาโดยเปิดเว็บพอร์ต 8080 จะเรียก Flask บน localhost โดยตรง

| เมธอดและเส้นทาง | การยืนยันตัวตน | หน้าที่ |
| --- | --- | --- |
| `GET /api/v1/health` | ไม่ต้องใช้ | ตรวจ Backend และบริการที่พึ่งพา |
| `POST /api/v1/auth/register` | ไม่ต้องใช้ | สมัครบัญชี |
| `POST /api/v1/auth/login` | ไม่ต้องใช้ | เข้าสู่ระบบและรับ JWT |
| `GET /api/v1/auth/me` | Bearer token | อ่านผู้ใช้ปัจจุบัน |
| `POST /api/v1/jobs/generate` | Bearer token | ส่งงานสร้างภาพ |
| `POST /api/v1/jobs/edit` | Bearer token | อัปโหลดและส่งงานแก้ไขภาพ |
| `GET /api/v1/jobs` | Bearer token | อ่านงานของผู้ใช้ปัจจุบัน |
| `GET /api/v1/jobs/{id}` | Bearer token | อ่านสถานะและลิงก์ผลลัพธ์ |
| `GET /media/{filename}` | ลิงก์ที่มีลายเซ็นใน main รุ่นนี้ | ดาวน์โหลดภาพ |

คำขอสร้างและแก้ไขภาพตอบ HTTP `202` เมื่อรับงานแล้ว Frontend ตรวจสถานะซ้ำประมาณทุก 1.5 วินาทีจนเป็น `completed` หรือ `failed` คิวใช้ thread pool ภายใน Flask จึงควรเปิด Backend เพียง 1 โปรเซสในการสาธิต

API ภายใน FastAPI มี `GET /health`, `POST /v1/generate` และ `POST /v1/edit` การสร้างและแก้ไขภาพต้องแนบ `X-LUMA-Service-Token` ซึ่งแยกจาก JWT ของผู้ใช้

ดูตัวอย่างใน [สัญญา API](docs/API_CONTRACT.md) ความสามารถใหม่บนสาขา Backend เช่น การดาวน์โหลดด้วย JWT และการกู้คิว ยังต้องรวมและทดสอบกับ main ก่อนใช้ในระบบรวม

## เริ่มทดสอบในเครื่องเดียว

ต้องมี Python 3.11 ขึ้นไป สำหรับโหมดพัฒนาไม่จำเป็นต้องติดตั้ง Nginx

1. เปิด PowerShell ที่โฟลเดอร์โครงงาน สร้างไฟล์กำหนดค่าเมื่อยังไม่มี หากมี `.env` แล้วให้แก้ไฟล์เดิม

   ```powershell
   Copy-Item backend/.env.example backend/.env
   Copy-Item ai-engine/.env.example ai-engine/.env
   ```

2. ตั้ง `AI_SERVICE_TOKEN` ให้ตรงกันทั้งสองไฟล์ กำหนด `SECRET_KEY` และ `JWT_SECRET_KEY` ของ Backend เป็นค่าสุ่มคนละค่า
3. เปิด WebUI Forge ผ่าน Stability Matrix พร้อม `--api --port 7860` หากทดสอบโดยไม่ใช้ Forge ให้ตั้ง `AI_PROVIDER=development-procedural` ใน `ai-engine/.env`
4. เปิด PowerShell แยก 3 หน้าต่าง แล้วเรียกหน้าต่างละคำสั่ง

   ```powershell
   ./scripts/run-ai.ps1
   ./scripts/run-backend.ps1
   ./scripts/run-frontend.ps1
   ```

5. เปิด `http://localhost:8080` สมัครสมาชิก เข้าสู่ระบบ แล้วทดลองสร้างและแก้ไขภาพ

สคริปต์บริการสร้าง `.venv` และติดตั้งไลบรารีให้ Frontend โหมดนี้เรียก `http://localhost:5000` จึงเหมาะกับการเปิดทุกบริการบนเครื่องเดียว

## ทดสอบด้วย Docker

เปิด Docker Desktop ให้พร้อม แล้วรันจากโฟลเดอร์โครงงาน

```powershell
docker compose up --build
```

เปิด `http://localhost` ข้อมูลขณะใช้งานอยู่ใน Docker volumes ค่า Compose ปัจจุบันใช้ `development-procedural` เพื่อทดสอบระบบโดยไม่ใช้โมเดลหรือ GPU

## ติดตั้งบน 3 เครื่องใน VLAN เดียวกัน

ทั้งสามเครื่องต้องติดต่อกันได้ใน VLAN ของห้องเรียน ไม่ต้องใช้ Tailscale หรือ port forwarding ออกอินเทอร์เน็ต IP `192.168.1.x` เป็นตัวอย่าง ให้แทนด้วย IP จริง

1. PC 1 สร้าง `ai-engine/.env` จาก `.env.vlan.example` แก้โทเคน เปิด Forge บน localhost แล้วเริ่ม FastAPI พอร์ต `8000`
2. PC 3 สร้าง `backend/.env` จาก `.env.vlan.example` แก้กุญแจและ `AI_SERVICE_URL` ให้ชี้ PC 1 เปิด Flask พอร์ต `5000` และเก็บ SQLite บน PC 3
3. PC 2 ติดตั้ง Nginx ตั้ง root ไปที่ Frontend จริงและ upstream ไปที่ PC 3 วาง `nginx.conf` กับ `luma.conf` ในโฟลเดอร์กำหนดค่าเดียวกัน แล้วตรวจด้วย `nginx.exe -t`
4. ตรวจว่า `AI_SERVICE_TOKEN` ของ PC 1 และ PC 3 ตรงกัน
5. อนุญาตไฟร์วอลล์ตามเส้นทาง PC 3 → PC 1 พอร์ต `8000`, PC 2 → PC 3 พอร์ต `5000` และเครื่องผู้ใช้ → PC 2 พอร์ต `80`
6. เริ่มตามลำดับ Forge → FastAPI → Flask → Nginx แล้วเปิดเว็บด้วย IP ของ PC 2
7. ตรวจการสมัครสมาชิก สร้างภาพ แก้ไขภาพ ดาวน์โหลด และแยกสิทธิ์ระหว่างบัญชีตาม [แผนทดสอบ](docs/TEST_PLAN.md)

ใช้ [คู่มือทดสอบ 3 เครื่อง](PROJECTLUMA_3PC_TEST_GUIDE.md) ส่งให้สมาชิก และอ่าน [รายละเอียดการติดตั้ง](docs/DEPLOYMENT.md) เพิ่มเติม

## การแบ่งงานและสาขา

| สาขา | งาน |
| --- | --- |
| `Frontend` | หน้าเว็บ HTML/CSS/JavaScript บน PC 2 |
| `Backend` | Flask ผู้ใช้ งาน SQLite และไฟล์ภาพบน PC 3 |
| `AiEngine` | FastAPI การเรียก Forge และโมเดลบน PC 1 |
| `Routing` | Nginx และเส้นทางคำขอบน PC 2 |
| `QA` | ชุดทดสอบ CI และการตรวจระบบร่วมกัน |
| `main` | โค้ดรวมสำหรับทดสอบครบระบบ |

แยกคอมมิตตามส่วนงานและรวมเข้า main เมื่อผ่านการตรวจ หมายเลขสมาชิกไม่ต้องตรงกับหมายเลข PC ผู้ดูแล Frontend และ Routing ใช้เครื่องให้บริการเดียวกันได้ ส่วน QA ตรวจทั้งระบบ

## Forge และบริการ AI

Stability Matrix ใช้ติดตั้งและเปิด Stable Diffusion WebUI Forge ตัว FastAPI แปลง `/v1/generate` เป็น `/sdapi/v1/txt2img` และ `/v1/edit` เป็น `/sdapi/v1/img2img` จากนั้นถอด Base64 ของภาพแล้วส่ง PNG ให้ Flask

FastAPI ทำงานผ่าน Uvicorn พอร์ต 8000 มีหน้าเอกสาร `http://127.0.0.1:8000/docs` บน PC 1 ส่วน Flask ใช้พอร์ต 5000 ดูแลบัญชี งาน และ SQLite อ่าน [คู่มือ AI](ai-engine/README.md) และ [คู่มือ Backend](backend/README.md) เพิ่มเติม

provider `development-procedural` ใช้ Pillow วาดภาพตัวอย่างและเอฟเฟกต์พื้นฐานสำหรับพัฒนาและทดสอบ ผลที่ได้จึงไม่ใช่ภาพจากโมเดล Generative AI ที่ผ่านการฝึก

## การตรวจโค้ด

ติดตั้งไลบรารีใน environment สำหรับพัฒนาแล้วตรวจจากโฟลเดอร์โครงงาน

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
node --check frontend/assets/app.js
docker compose config --quiet
```

ชุดทดสอบใช้บริการจำลอง จึงต้องทดสอบ Forge จริงและการส่งภาพข้าม 3 เครื่องก่อนสาธิตด้วย

## การดูแลค่าลับและข้อมูล

- ไม่เก็บ `.env` โทเคน รหัสผ่าน ฐานข้อมูล ภาพอัปโหลด หรือผลลัพธ์ลง Git
- Backend จำกัดขนาดอัปโหลดและตรวจรูปแบบภาพ
- จำกัดผู้ที่ติดต่อ FastAPI และเก็บ Forge บน localhost ของ PC 1
- HTTP ในการตั้งค่านี้ไม่ได้เข้ารหัสข้อมูลระหว่างส่ง หากใช้นอกเครือข่ายที่เชื่อถือได้ต้องเตรียม HTTPS
