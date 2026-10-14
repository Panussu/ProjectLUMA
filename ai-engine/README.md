# LUMA AI Engine

บริการ FastAPI รับงานจาก Backend และเรียก Forge หรือ procedural provider ปรับปรุงวันที่ 14 ตุลาคม 2026 ตาม integrated `main` ที่ `5b52b9e`

## Providers และโครงสร้าง

- `forge`: เรียก Stable Diffusion WebUI Forge สำหรับงานสร้าง/แก้ไขและความสามารถที่ Forge รองรับ
- `development-procedural`: ใช้ Pillow และ CPU สำหรับทดสอบการเชื่อมต่อและวงจรงาน ไม่ใช่ trained image generation หรือ neural upscaling

`app.py` ประกอบ API; `queue_manager.py` จัดคิวและสถานะ; `forge_client.py` / `dev_provider.py` เชื่อม provider; validators ตรวจข้อมูล ส่วน scanner, filters, PNG parser และ tag service รองรับเครื่องมือภาพและ catalog

## เริ่มใช้งาน

รันภายใน `ai-engine`:

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

แก้ `.env` ให้ `AI_SERVICE_TOKEN` เป็นค่าสุ่มเดียวกับ Backend เลือก provider และตั้ง paths จริง จากนั้นเปิด:

```powershell
./.venv/Scripts/python.exe app.py
```

ค่า native เริ่มต้นคือ `HOST=127.0.0.1`, `PORT=8000` เปิด OpenAPI ที่ `http://127.0.0.1:8000/docs` หรือใช้ `./scripts/run-ai.ps1` จาก root เพื่อเตรียม environment และเปิดบริการ

## Forge

1. ติดตั้งและเปิด Forge เช่นผ่าน Stability Matrix พร้อม `--api --port 7860`
2. เมื่ออยู่เครื่องเดียวกัน ให้รับเฉพาะ localhost โดยไม่เพิ่ม `--listen`
3. ตรวจ `http://127.0.0.1:7860/docs` ว่ามี `/sdapi/v1/txt2img` และ `/sdapi/v1/img2img`
4. ตั้ง `AI_PROVIDER=forge` และ `FORGE_URL=http://127.0.0.1:7860`
5. หากใช้ `--api-auth` ตั้ง `FORGE_USERNAME` / `FORGE_PASSWORD` ให้ตรงกัน

Engine แปลงคำขอ LUMA เป็น Forge request และถอดภาพ Base64 เป็นผลลัพธ์ภาพ หลีกเลี่ยงการสร้างงานผ่าน Forge UI พร้อมกับ LUMA เพราะ Forge progress/interrupt ใช้สถานะร่วมกัน

## Configuration

| ค่า | การใช้งาน/ค่าเริ่มต้น |
| --- | --- |
| `AI_PROVIDER` | native example เป็น `forge`; Compose เริ่มต้น procedural |
| `AI_SERVICE_TOKEN` | credential ร่วมกับ Backend แยกจาก JWT ผู้ใช้ |
| `FORGE_URL` | native `http://127.0.0.1:7860` |
| `FORGE_USERNAME`, `FORGE_PASSWORD` | ใช้เมื่อ Forge เปิด API authentication |
| `MODELS_DIR`, `LORAS_DIR` | แก้ paths ตัวอย่างให้ตรงกับไฟล์จริง |
| `FORGE_CHECKPOINT` | checkpoint ที่เลือกเมื่อกำหนด |
| `FORGE_SAMPLER`, `FORGE_CFG_SCALE`, `FORGE_EDIT_STEPS` | เริ่มต้น Euler, 7, 20 |
| `MAX_CONCURRENT_GENERATIONS` | เริ่มต้น 1; Forge ถูกจำกัดเป็น 1 |
| `MAX_QUEUE_CAPACITY`, `QUEUE_TIMEOUT_SECONDS` | เริ่มต้น 20, 180 วินาที |
| `MAX_CONTENT_LENGTH` | เริ่มต้น 16 MiB |
| `FASTAPI_DEBUG` | เริ่มต้นปิด |

ข้อมูล generation ต้องผ่านการตรวจ dimensions/steps และ edit options มี validation การประมวลผลภาพมีขอบเขตจำกัด และ optional metadata ที่ผิดรูปแบบไม่ควรทำให้ทั้งคำขอล้มเหลว

## API และ job identity

| เส้นทาง | หน้าที่ |
| --- | --- |
| `GET /health` | ตรวจบริการ |
| `POST /v1/generate`, `/v1/edit` | สร้างและแก้ไขภาพ |
| `/v1/models`, `/v1/loras`, `/v1/samplers`, `/v1/schedulers` | Catalog |
| `/v1/settings`, `/v1/styles` | Settings และ styles |
| `/v1/queue/status`, `/v1/progress` | คิวและ progress |
| `POST /v1/interrupt`, `/v1/skip` | ควบคุมงานด้วย `job_id` |
| `/v1/upscalers`, `/v1/upscale`, `/v1/interrogate` | เครื่องมือของ provider |
| `/v1/filters`, `/v1/process`, `/v1/png-info`, `/v1/tags` | Filters และ metadata |

งานสร้าง/แก้ไขและ private service endpoints ใช้ `X-LUMA-Service-Token` Backend ส่ง `X-LUMA-Job-ID` เพื่อผูกการควบคุมกับงานที่ถูกต้อง Progress/interrupt/skip ใช้ `job_id` ตาม contract คิวตรวจงาน active/cancelled; คิวเต็มตอบ 429 และรอเกิน timeout ตอบ 504

Health และ utility endpoints บางรายการมี authentication ต่างจาก private endpoints ตรวจ OpenAPI ก่อนเรียก ไม่ควรเปิด service token ให้ browser ใช้โดยตรง Backend เป็นผู้ตรวจ JWT และเจ้าของงาน ดู [API contract](../docs/API_CONTRACT.md)

## Docker และหลายเครื่อง

Production Compose ส่ง `FORGE_URL`, username และ password จาก configuration โดย URL เริ่มต้นคือ `http://host.docker.internal:7860` ตรวจว่า container เข้าถึง Forge ได้ และ mount model/LoRA directories เมื่อต้องอ่านไฟล์ host Paths บน Windows ไม่ได้ปรากฏใน container อัตโนมัติ

สำหรับ PC 1 ตั้ง listen host ตาม network ที่ต้องการ เช่น `0.0.0.0` แล้วให้ Backend ใช้ IP จริงของ PC 1 ที่ port 8000 พร้อม service token เดียวกัน ใช้ `0.0.0.0` สำหรับ binding เท่านั้น ดู [deployment](../docs/DEPLOYMENT.md) และ [สามเครื่อง](../docs/PROJECTLUMA_3PC_TEST_GUIDE.md)

## Verification

จาก root ติดตั้ง `requirements-dev.txt` ลงใน test environment แล้วรัน:

```powershell
python -m pytest -q --tb=short
node --test tests/test_frontend.cjs
```

การตรวจ README ครั้งนี้รันซ้ำ Python **109 ผ่าน** และ frontend **15 ผ่าน** [Latest audit](../docs/WEBAPP_AUDIT_2026-10-14.md) บันทึก HTTP/API 78 และ Chromium 53 ผ่านแยกต่างหาก โดยใช้ procedural provider และ fixtures ยังไม่ได้ทดสอบ real Forge/GPU, container build/runtime หรือระบบสามเครื่องจริง ดู [root README](../README.md) สำหรับ setup และผลทดสอบรวม
