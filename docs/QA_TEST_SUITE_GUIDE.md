# 🧪 คู่มือและเอกสารอ้างอิงชุดทดสอบประกันคุณภาพ (QA Test Suite Architecture & Technical Reference)
**ProjectLUMA (Learning-based Universal Media Artist)**

---

## 📌 1. ปรัชญาและขอบเขตการทดสอบ (Testing Philosophy & Scope)

ชุดทดสอบของ ProjectLUMA ได้รับการออกแบบตามหลัก **Test-Driven QA Standards** โดยมุ่งเน้นการตรวจรับรองความถูกต้อง ความปลอดภัย และเสถียรภาพของระบบโดยไม่ต้องพึ่งพาฮาร์ดแวร์ GPU ในกระบวนการ CI/CD (Continuous Integration):

1. **Deterministic Mocking:** ใช้ Mock / Procedural Provider เพื่อทดสอบ API Flow โดยผลลัพธ์ของภาพ PNG และ Seed มีความคงที่ 100%
2. **Security & Boundary Enforcement:** ตรวจสอบสิทธิ์ Bearer Token, Service Token, ป้องกันการอ่านข้อมูลข้ามบัญชี (User Isolation), และการปฏิเสธพารามิเตอร์ที่ผิดเงื่อนไข
3. **5-Algorithm Mathematical Verification:** พิสูจน์ความถูกต้องของอัลกอริทึมดิจิทัลทั้ง 5 ตามสูตรคำนวณสากล

---

## 🤖 2. โครงสร้างชุดทดสอบอัตโนมัติ (Automated Pytest Suite Details)

ชุดทดสอบอัตโนมัติประกอบด้วย 2 โมดูลหลัก รวม 11 กรณีทดสอบ (22 Assertions):

### 2.1 ชุดทดสอบ Backend API (`tests/test_backend_api.py`)

| รหัสทดสอบ | ชื่อฟังก์ชันทดสอบ | รายละเอียดวัตถุประสงค์ | เงื่อนไขการผ่าน |
| :---: | :--- | :--- | :--- |
| **TC-BE-001** | `test_registration_login_and_current_user` | ตรวจสอบการสมัครสมาชิก ห้ามใช้ Username ซ้ำ (Case-insensitive) และเข้าสู่ระบบได้ด้วย JWT | HTTP 409 เมื่อชื่อซ้ำ / HTTP 200 เมื่อเข้าสู่ระบบสำเร็จ |
| **TC-BE-002** | `test_invalid_registration_is_rejected` | ตรวจสอบการปฏิเสธชื่อผู้ใช้หรือรหัสผ่านสั้นเกินไป | HTTP 400 Validation Error |
| **TC-BE-003** | `test_generate_job_completes_and_media_link_works` | สั่งสร้างภาพ ตอบ HTTP 202 Polling งานเสร็จ และโหลดภาพผ่านลิงก์สื่อที่มีลายเซ็นได้ | HTTP 202 -> 200 และไบต์ภาพตรงกัน 100% |
| **TC-BE-004** | `test_edit_job_accepts_valid_image` | อัปโหลดภาพแบบ `multipart/form-data` และประมวลผลสำเร็จ | HTTP 202 Accepted และ Job Status = `completed` |
| **TC-BE-005** | `test_jobs_are_isolated_between_users` | ตรวจสอบ Data Isolation (ผู้ใช้ B ไม่สามารถอ่านงานของผู้ใช้ A ได้) | HTTP 404 Not Found (Security Boundary) |
| **TC-BE-006** | `test_protected_routes_require_authentication` | ปฏิเสธการเข้าถึง API ส่วนตัวเมื่อไม่ได้แนบ Bearer Token | HTTP 401 Unauthorized |

---

### 2.2 ชุดทดสอบ AI Engine Service (`tests/test_ai_service.py`)

| รหัสทดสอบ | ชื่อฟังก์ชันทดสอบ | รายละเอียดวัตถุประสงค์ | เงื่อนไขการผ่าน |
| :---: | :--- | :--- | :--- |
| **TC-AI-001** | `test_health_is_public` | ตรวจสอบ Endpoint `/health` สามารถเรียกดูได้แบบ Public | HTTP 200 OK |
| **TC-AI-002** | `test_fastapi_exposes_the_private_contract_in_openapi` | ตรวจสอบ OpenAPI Spec มี Route `/health`, `/v1/generate`, `/v1/edit` ครบถ้วน | OpenAPI Schema ถูกต้อง |
| **TC-AI-003** | `test_private_endpoint_rejects_missing_token` | ปฏิเสธคำขอที่ไม่แนบ `X-LUMA-Service-Token` | HTTP 401 Unauthorized |
| **TC-AI-004** | `test_generate_returns_repeatable_png` | ตรวจสอบภาพ PNG ที่ผลิตจาก Seed เดียวกันต้องมีขนาดและไบต์ตรงกัน 100% | Deterministic Byte Equality |
| **TC-AI-005** | `test_generation_dimensions_are_validated` | ปฏิเสธภาพที่มีขนาดกว้าง/ยาว ไม่เป็นพหุคูณของ 64 | HTTP 400 Bad Request |
| **TC-AI-006** | `test_edit_returns_png` | ตรวจสอบการส่งคืนภาพแก้ไขในรูปแบบ PNG | HTTP 200 OK Image Stream |
| **TC-AI-007** | `test_forge_generate_translates_payload` | ตรวจสอบการแปลพารามิเตอร์ส่งต่อไปยัง SD WebUI Forge (`/sdapi/v1/txt2img`) | HTTP 200 OK |
| **TC-AI-008** | `test_forge_edit_sends_base64_source_image` | ตรวจสอบการแปลงภาพต้นฉบับเป็น Base64 ส่งไปยัง Forge (`/sdapi/v1/img2img`) | Base64 Encoding Verified |
| **TC-AI-009** | `test_forge_health_reports_unavailable_provider` | ตรวจสอบการรายงาน HTTP 503 เมื่อไม่สามารถเชื่อมต่อ Forge ได้ | HTTP 503 Service Unavailable |

---

## 📐 3. สูตรทางคณิตศาสตร์ของการทดสอบ 5 อัลกอริทึม (Mathematical Verification)

$$\begin{aligned}
\text{1. Grayscale (ITU-R BT.601):} \quad & Y = 0.299R + 0.587G + 0.114B \\
\text{2. Edge Detection (Laplacian):} \quad & K = \begin{bmatrix} 0 & 1 & 0 \\ 1 & -4 & 1 \\ 0 & 1 & 0 \end{bmatrix} \\
\text{3. Gaussian Blur Kernel:} \quad & G(x,y) = \frac{1}{2\pi\sigma^2} e^{-\frac{x^2+y^2}{2\sigma^2}} \\
\text{4. Color Inversion:} \quad & I_{out}(x,y) = 255 - I_{in}(x,y) \\
\text{5. Super-Resolution (Lanczos):} \quad & L(x) = \text{sinc}(x)\text{sinc}(x/a)
\end{aligned}$$

---

## ⚡ 4. วิธีการสั่งรันชุดทดสอบ (QA Execution Manual)

เปิด PowerShell ที่โฟลเดอร์หลัก แล้วสั่งรันด้วยสคริปต์อัตโนมัติ:
```powershell
./scripts/run-all-tests.ps1
```

หรือใช้คำสั่ง Pytest โดยตรง:
```powershell
python -m pytest --tb=short
```

---
**เอกสารกำกับ QA Engineering Team (ProjectLUMA)**
