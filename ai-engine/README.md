# LUMA AI Engine

บริการ FastAPI ภายในบน PC 1 รับคำขอจาก Flask แล้วเชื่อม Stable Diffusion WebUI Forge ที่ติดตั้งและเปิดผ่าน Stability Matrix

## ตั้งค่า Stability Matrix และ Forge

1. ติดตั้งแพ็กเกจ Stable Diffusion WebUI Forge ใน Stability Matrix
2. เพิ่มอาร์กิวเมนต์ `--api --port 7860` ตอนเปิดแพ็กเกจ
3. เมื่อ FastAPI และ Forge อยู่บนเครื่องเดียวกัน ให้ Forge รับเฉพาะ localhost โดยไม่เพิ่ม `--listen`
4. เปิด Forge และตรวจที่ `http://127.0.0.1:7860/docs` ว่ามี `/sdapi/v1/txt2img` และ `/sdapi/v1/img2img`
5. สร้าง `.env` จากตัวอย่างเมื่อยังไม่มี ตั้ง `AI_PROVIDER=forge` และตั้ง `AI_SERVICE_TOKEN` ให้ตรงกับ Backend

FastAPI แปลงคำขอ LUMA เป็นรูปแบบของ Forge ถอด Base64 ของภาพ แล้วตอบ PNG ให้ Backend หาก Forge เปิด `--api-auth` ให้ตั้ง `FORGE_USERNAME` และ `FORGE_PASSWORD` ด้วย

เปิด `http://127.0.0.1:8000/docs` บนเครื่อง AI เพื่อดูเอกสารและทดลองเรียก API การสร้างและแก้ไขภาพยังต้องใช้ส่วนหัว `X-LUMA-Service-Token`

## เริ่มในเครื่องเดียว

เปิด PowerShell ในโฟลเดอร์ `ai-engine` แล้วติดตั้งไลบรารี หากมี `.env` แล้วให้แก้ไฟล์เดิมแทนการคัดลอกทับ

```powershell
python -m venv .venv
./.venv/Scripts/pip.exe install -r requirements.txt
Copy-Item .env.example .env
./.venv/Scripts/python.exe app.py
```

## Provider สำหรับพัฒนา

ตั้ง `AI_PROVIDER=development-procedural` เพื่อทดสอบโทเคน เส้นทาง อัปโหลด คิว จัดเก็บ และหน้าเว็บโดยไม่ต้องมี Forge หรือ GPU โหมดนี้ใช้ Pillow สร้างภาพตัวอย่างและเอฟเฟกต์พื้นฐาน ไม่ใช่โมเดล Generative AI ที่ผ่านการฝึก

## PC 1 ใน VLAN ห้องเรียน

Forge ใช้ `127.0.0.1:7860` ส่วน FastAPI รับการเชื่อมต่อที่ `0.0.0.0:8000` เพื่อให้ Flask บน PC 3 ติดต่อได้ เครื่องอื่นต้องเรียก IP จริงของ PC 1 ไม่ใช่ 0.0.0.0

หากยังไม่มีไฟล์กำหนดค่า ให้เริ่มจากตัวอย่าง VLAN แล้วแก้โทเคนก่อนรัน

```powershell
Copy-Item .env.vlan.example .env
./.venv/Scripts/python.exe app.py
```

ตรวจ IP ด้วย `ipconfig` ค่า `192.168.1.30` เป็นตัวอย่าง อนุญาต TCP 8000 จาก PC 3 และเก็บพอร์ต Forge 7860 สำหรับการเชื่อมต่อในเครื่องเดียวกัน

