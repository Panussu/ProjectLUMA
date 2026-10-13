# 📄 ข้อกำหนดและสัญญา API (ProjectLUMA API Specification & Contract)
**LUMA (Learning-based Universal Media Artist)**  
**Version:** 1.0.0 | **Protocol:** HTTP/1.1 REST API | **Format:** JSON / Multipart-Form / Image-PNG

---

## 📌 1. ภาพรวมและโปรโตคอลความปลอดภัย (Authentication & Security Overview)

ระบบ ProjectLUMA แยกการสื่อสารออกเป็น 2 ชั้นความปลอดภัย:
1. **Public/Client API (Flask Backend):** รองรับการเรียกจากผู้ใช้ผ่าน HTTP Header `Authorization: Bearer <JWT_TOKEN>`
2. **Private Inter-Service API (FastAPI AI Engine):** สื่อสารภายในระหว่าง Backend และ AI Engine ป้องกันด้วย HTTP Header `X-LUMA-Service-Token: <SHARED_SERVICE_TOKEN>`

---

## 🔑 2. ระบบระบุตัวตน Backend API (Authentication Endpoints)

### 2.1 สมัครสมาชิก (Register)
* **Endpoint:** `POST /api/v1/auth/register`
* **Content-Type:** `application/json`
* **Request Body:**
  ```json
  {
    "username": "student.one",
    "password": "correct-horse-battery"
  }
  ```
* **Validation Rules:**
  * `username`: ความยาว 3 - 40 ตัวอักษร (ระบบแปลงเป็นตัวพิมพ์เล็ก Case-insensitive)
  * `password`: ความยาวอย่างน้อย 8 ตัวอักษร
* **Response (201 Created):**
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "user": {
      "id": 1,
      "username": "student.one",
      "created_at": "2026-10-04T10:00:00Z"
    }
  }
  ```
* **Error Responses:**
  * `400 Bad Request`: `{"error": {"code": "validation_error", "message": "Username and password length rules violated"}}`
  * `409 Conflict`: `{"error": {"code": "conflict", "message": "Username already exists"}}`

---

### 2.2 เข้าสู่ระบบ (Login)
* **Endpoint:** `POST /api/v1/auth/login`
* **Content-Type:** `application/json`
* **Request Body:**
  ```json
  {
    "username": "student.one",
    "password": "correct-horse-battery"
  }
  ```
* **Response (200 OK):**
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "user": {
      "id": 1,
      "username": "student.one"
    }
  }
  ```
* **Error Response (401 Unauthorized):**
  ```json
  {
    "error": {
      "code": "invalid_credentials",
      "message": "Invalid username or password"
    }
  }
  ```

---

### 2.3 ตรวจสอบข้อมูลผู้ใช้ปัจจุบัน (Current User Profile)
* **Endpoint:** `GET /api/v1/auth/me`
* **Headers:** `Authorization: Bearer <JWT_TOKEN>`
* **Response (200 OK):**
  ```json
  {
    "user": {
      "id": 1,
      "username": "student.one"
    }
  }
  ```

---

## 🎨 3. ระบบจัดการงานประมวลผล Backend Jobs API

### 3.1 สั่งสร้างภาพจากข้อความ (Text-to-Image Generation Job)
* **Endpoint:** `POST /api/v1/jobs/generate`
* **Headers:** `Authorization: Bearer <JWT_TOKEN>`
* **Content-Type:** `application/json`
* **Request Body:**
  ```json
  {
    "prompt": "a futuristic cyberpunk cityscape at night, neon lights, 8k resolution",
    "negative_prompt": "blurry, low quality, distorted",
    "width": 512,
    "height": 512,
    "steps": 20,
    "cfg_scale": 7.0,
    "seed": 42
  }
  ```
* **Validation Rules:**
  * `width`, `height`: ต้องเป็นพหุคูณของ 64 (เช่น 512, 768, 1024)
  * `steps`: 1 - 50
  * `cfg_scale`: 1.0 - 20.0
* **Response (202 Accepted):**
  ```json
  {
    "job": {
      "id": "job_984f2a11-50e4-4c80-a352-82ab7c31d102",
      "status": "processing",
      "job_type": "generate",
      "created_at": "2026-10-04T10:05:00Z"
    }
  }
  ```

---

### 3.2 สั่งแก้ไขภาพ (Image-to-Image Edit Job)
* **Endpoint:** `POST /api/v1/jobs/edit`
* **Headers:** `Authorization: Bearer <JWT_TOKEN>`
* **Content-Type:** `multipart/form-data`
* **Form Parameters:**
  * `prompt` (string, required): คำสั่งแก้ไข
  * `strength` (float, optional, default: 0.65): ค่า Denoising (0.0 - 1.0)
  * `seed` (int, optional): ตัวเลขสุ่ม
  * `image` (file, required): ไฟล์ภาพ PNG, JPEG, WebP (สูงสุด 16 MiB)
* **Response (202 Accepted):**
  ```json
  {
    "job": {
      "id": "job_119ab32c-7721-419b-b271-70099818ab44",
      "status": "processing",
      "job_type": "edit",
      "created_at": "2026-10-04T10:06:00Z"
    }
  }
  ```

---

### 3.3 ติดตามผลและสถานะงาน (Get Job Details & Polling)
* **Endpoint:** `GET /api/v1/jobs/{job_id}`
* **Headers:** `Authorization: Bearer <JWT_TOKEN>`
* **Response (200 OK - Processing):**
  ```json
  {
    "job": {
      "id": "job_984f2a11-50e4-4c80-a352-82ab7c31d102",
      "status": "processing",
      "progress": 45,
      "eta_seconds": 3
    }
  }
  ```
* **Response (200 OK - Completed):**
  ```json
  {
    "job": {
      "id": "job_984f2a11-50e4-4c80-a352-82ab7c31d102",
      "status": "completed",
      "provider": "forge",
      "seed": 42,
      "result_url": "/media/sig_a9f8b7c6d5e4.png?expires=1791196800&signature=abc123..."
    }
  }
  ```

---

### 3.4 เรียกดูประวัติงานทั้งหมดของผู้ใช้ (List User Jobs)
* **Endpoint:** `GET /api/v1/jobs`
* **Headers:** `Authorization: Bearer <JWT_TOKEN>`
* **Response (200 OK):**
  ```json
  {
    "jobs": [
      {
        "id": "job_984f2a11-50e4-4c80-a352-82ab7c31d102",
        "status": "completed",
        "job_type": "generate",
        "prompt": "a futuristic cyberpunk cityscape...",
        "created_at": "2026-10-04T10:05:00Z",
        "result_url": "/media/sig_a9f8b7c6d5e4.png..."
      }
    ]
  }
  ```

---

## 🤖 4. สัญญาการสื่อสารระดับบริการ AI Engine API (FastAPI AI Contract)

### 4.1 ตรวจสอบความพร้อมบริการ AI (Public Health Check)
* **Endpoint:** `GET /health`
* **Authentication:** ไม่ต้องใช้ (Public)
* **Response (200 OK):**
  ```json
  {
    "status": "ok",
    "service": "luma-ai",
    "provider": "forge",
    "version": "1.0.0"
  }
  ```
* **Response (503 Service Unavailable):**
  ```json
  {
    "status": "unavailable",
    "service": "luma-ai",
    "provider": "webui-forge",
    "error": "Cannot connect to Stable Diffusion WebUI Forge on http://127.0.0.1:7860"
  }
  ```

---

### 4.2 คำสั่งสร้างภาพภายใน (Private Text-to-Image Generation)
* **Endpoint:** `POST /v1/generate`
* **Headers:** `X-LUMA-Service-Token: <SHARED_SERVICE_TOKEN>`
* **Request Body:**
  ```json
  {
    "prompt": "a paper city in soft daylight",
    "negative_prompt": "blurry",
    "width": 512,
    "height": 512,
    "steps": 20,
    "seed": 99
  }
  ```
* **Response (200 OK):**
  * **Content-Type:** `image/png`
  * **Headers:**
    * `X-LUMA-Seed: 99`
    * `X-LUMA-Provider: forge`
  * **Body:** Binary Stream of PNG Image Data

---

### 4.3 คำสั่งแก้ไขภาพภายใน (Private Image-to-Image Edit)
* **Endpoint:** `POST /v1/edit`
* **Headers:** `X-LUMA-Service-Token: <SHARED_SERVICE_TOKEN>`
* **Content-Type:** `multipart/form-data`
* **Response (200 OK):**
  * **Content-Type:** `image/png`
  * **Headers:** `X-LUMA-Seed: <SEED>`
  * **Body:** Binary Stream of PNG Image Data

---

### 4.4 คำสั่งประมวลผล 5 อัลกอริทึม (5 Digital Image Processing Endpoint)
* **Endpoint:** `POST /process`
* **Headers:** `X-LUMA-Service-Token: <SHARED_SERVICE_TOKEN>`
* **Content-Type:** `multipart/form-data`
* **Form Parameters:**
  * `operation` (string): `grayscale` | `edge` | `blur` | `invert`
  * `image` (file): ไฟล์ภาพต้นฉบับ
* **Response (200 OK):** Binary Stream of processed PNG image.

---

### 4.5 คำสั่งขยายภาพความละเอียดสูง (Private Super-Resolution Upscale)
* **Endpoint:** `POST /v1/upscale`
* **Headers:** `X-LUMA-Service-Token: <SHARED_SERVICE_TOKEN>`
* **Content-Type:** `multipart/form-data`
* **Form Parameters:**
  * `scale` (int): `2` หรือ `4`
  * `image` (file): ไฟล์ภาพต้นฉบับ
* **Response (200 OK):** Binary Stream of Upscaled PNG image (Lanczos Sinc Resampling).

---

## 🔒 5. โครงสร้างข้อผิดพลาดมาตรฐาน (Standardized Error Schema)

ทุก Endpoint คืนรูปแบบ Error JSON เดียวกันในกรณีประมวลผลไม่สำเร็จ:

```json
{
  "error": {
    "code": "unauthorized | validation_error | not_found | conflict | payload_too_large | ai_unavailable",
    "message": "ข้อความอธิบายสาเหตุข้อผิดพลาดสำหรับผู้ใช้หรือทีมพัฒนา"
  }
}
```

| HTTP Code | Error Code | สาเหตุ |
| :---: | :--- | :--- |
| **400** | `validation_error` | ข้อมูลนำเข้าไม่ถูกต้อง (เช่น กว้าง/ยาว ไม่หารด้วย 64) |
| **401** | `unauthorized` | ไม่ได้แนบ Bearer Token หรือ `X-LUMA-Service-Token` ไม่ถูกต้อง |
| **404** | `not_found` | ไม่พบทรัพยากร หรือพยายามอ่านงานของผู้ใช้คนอื่น (Data Isolation) |
| **409** | `conflict` | สมัครสมาชิกด้วย Username ที่มีอยู่ในระบบแล้ว |
| **413** | `payload_too_large` | ไฟล์ภาพที่อัปโหลดมีขนาดเกิน 16 MiB |
| **503** | `ai_unavailable` | ไม่สามารถติดต่อ AI Engine หรือ Stable Diffusion Forge ได้ |

---
*เอกสารนี้ได้รับการตรวจสอบและรับรองโดย QA & DevOps Lead (ProjectLUMA)*
