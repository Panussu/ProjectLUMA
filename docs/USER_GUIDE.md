# 📖 คู่มือการใช้งานระบบฉบับสมบูรณ์ (ProjectLUMA User & Operation Manual)
**LUMA (Learning-based Universal Media Artist)**

---

## 📌 1. ภาพรวมของระบบ (System Overview)

**ProjectLUMA** เป็นเว็บแอปพลิเคชันปัญญาประดิษฐ์สำหรับการสร้างภาพจากข้อความ (Text-to-Image), การแก้ไขภาพ (Image-to-Image), และการประมวลผลภาพด้วย 5 อัลกอริทึมดิจิทัล โดยรองรับการทำงานทั้งบนเครื่องเดียว (Single-machine), คอนเทนเนอร์ (Docker Compose), และแบบแยก 3 เครื่องบนวงเครือข่ายเดียวกัน (3-PC Same-VLAN Architecture)

### 🌟 ฟีเจอร์หลักของระบบ (Key Features)
1. **ระบบสมัครสมาชิกและการยืนยันตัวตน (Authentication & JWT):** ระบบจัดการผู้ใช้ รักษาความปลอดภัยด้วย JWT Bearer Token และแยกข้อมูลงานของผู้ใช้แต่ละคน (Data Isolation)
2. **ระบบสร้างภาพจากข้อความ (Text-to-Image Generation):**
   * รองรับการใส่ Prompt, Negative Prompt, Seed, Steps, และ CFG Scale
   * ปรับขนาดภาพอัตโนมัติ (ความกว้างxยาว ต้องหารด้วย 64 ลงตัว)
   * เลือกโมเดล (Checkpoints), LoRA พร้อมปรับน้ำหนัก (Weight), และประเภท Sampler / Scheduler
   * 10 Style Presets สำเร็จรูป (เช่น Anime, Cyberpunk, Photorealistic, Pixel Art, ฯลฯ)
3. **ระบบแก้ไขภาพ (Image-to-Image Edit):**
   * อัปโหลดภาพต้นฉบับ (PNG, JPEG, WebP) ขนาดสูงสุด 16MB
   * ปรับค่า Denoising Strength (0.0 - 1.0) ร่วมกับคำสั่งแก้ไข
4. **5 อัลกอริทึมการประมวลผลภาพดิจิทัล (5 Core Image Algorithms):**
   * **Grayscale Transform (BT.601):** แปลงภาพเป็นขาวดำตามความไวแสงของตามนุษย์
   * **Edge Detection (Convolution):** สกัดเส้นขอบด้วย 3x3 Spatial Convolution Filter
   * **Gaussian Blur Smoothing:** ลดสัญญาณรบกวนความถี่สูง ปรับภาพให้นุ่มนวล
   * **Color Inversion:** คำนวณสีคู่ตรงข้ามแบบ Pointwise Arithmetic Negation
   * **Image Super-Resolution (Lanczos Resampling):** ขยายภาพ 2x - 4x ด้วย Anti-aliasing
5. **ระบบติดตามสถานะและการประมวลผลแบบเรียลไทม์ (Live Progress & Queue):**
   * แสดงสถานะ Polling (Queued -> Processing -> Completed)
   * แสดงเปอร์เซ็นต์ความคืบหน้า และประมาณเวลาที่เหลือ
   * ปุ่มยกเลิกงานประมวลผล (Cancel Generation)
6. **ระบบดาวน์โหลดและประวัติงาน (Job History & Signed Media Links):**
   * คลังประวัติผลงานส่วนตัว พร้อมลิงก์ดาวน์โหลดปลอดภัย

---

## 💻 2. สิ่งที่ต้องเตรียมก่อนใช้งาน (Prerequisites)

* **ระบบปฏิบัติการ:** Windows 10 / Windows 11
* **ซอฟต์แวร์พื้นฐาน:**
  * Git (เวอร์ชัน 2.40 ขึ้นไป)
  * Python 3.11 ขึ้นไป (แนะนำ Python 3.12)
* **สำหรับการใช้งานร่วมกับ AI จริง (Optional):**
  * Stability Matrix หรือ Stable Diffusion WebUI Forge (เปิดพอร์ต `--api --port 7860`)
* **สำหรับการรันผ่าน Docker (Optional):**
  * Docker Desktop for Windows

---

## 🚀 3. วิธีการเริ่มใช้งานระบบ (System Startup Options)

เลือกวิธีเริ่มใช้งานระบบตามสภาพแวดล้อมที่คุณสะดวก:

### 🔹 วิธีที่ 1: รันในเครื่องเดียวแบบ Local Development (แนะนำสำหรับทดสอบโค้ด)
เปิด PowerShell หน้าต่างใหม่ 3 หน้าต่าง ที่โฟลเดอร์หลัก `ProjectLUMA` แล้วรันสคริปต์ทีละหน้าต่าง:

* **หน้าต่างที่ 1 (เริ่ม AI Engine):**
  ```powershell
  ./scripts/run-ai.ps1
  ```
  *(ระบบจะสร้าง `.venv` และเปิดบริการ FastAPI บน `http://localhost:8000`)*

* **หน้าต่างที่ 2 (เริ่ม Backend API):**
  ```powershell
  ./scripts/run-backend.ps1
  ```
  *(ระบบจะสร้าง `.venv` และเปิดบริการ Flask บน `http://localhost:5000`)*

* **หน้าต่างที่ 3 (เริ่ม Frontend Web Server):**
  ```powershell
  ./scripts/run-frontend.ps1
  ```
  *(เปิดให้บริการหน้าเว็บ static บน `http://localhost:8080`)*

👉 **การเข้าใช้งาน:** เปิดเบราว์เซอร์แล้วไปที่ `http://localhost:8080`

---

### 🔹 วิธีที่ 2: รันผ่าน Docker Compose (คำสั่งเดียวจบ)
เปิด PowerShell ที่โฟลเดอร์หลัก แล้วใช้คำสั่ง:

```powershell
./scripts/deploy.ps1 -Build
```
หรือใช้คำสั่ง Docker โดยตรง:
```powershell
docker compose up --build -d
```

👉 **การเข้าใช้งาน:** เปิดเบราว์เซอร์แล้วไปที่ `http://localhost`

---

### 🔹 วิธีที่ 3: ติดตั้งและเปิดรันแบบ 3 เครื่องบนวง VLAN (สำหรับสาธิต 3-PC Setup)
สมมุติ IP ตัวอย่างในเครือข่าย:
* **PC 1 (เครื่อง AI Engine):** `192.168.1.30`
* **PC 2 (เครื่อง Nginx Frontend):** `192.168.1.10`
* **PC 3 (เครื่อง Backend):** `192.168.1.20`

1. **PC 1 (ฝั่ง AI):**
   * เปิด WebUI Forge พอร์ต `7860`
   * สร้าง `ai-engine/.env` กำหนด `AI_SERVICE_TOKEN`
   * รันสคริปต์ `./scripts/run-ai.ps1` (พอร์ต `8000`)

2. **PC 3 (ฝั่ง Backend):**
   * สร้าง `backend/.env` กำหนด `AI_SERVICE_URL=http://192.168.1.30:8000` และตั้งค่า `AI_SERVICE_TOKEN` ให้ตรงกับ PC 1
   * รันสคริปต์ `./scripts/run-backend.ps1` (พอร์ต `5000`)

3. **PC 2 (ฝั่ง Frontend & Nginx):**
   * ติดตั้ง Nginx วางไฟล์ `nginx/nginx.conf` และ `nginx/luma.conf`
   * กำหนด upstream ใน Nginx ให้ชี้ไปที่ PC 3 (`192.168.1.20:5000`)
   * รันบริการ Nginx (พอร์ต `80`)

👉 **การเข้าใช้งาน:** เครื่องผู้ใช้ในวง LAN เปิดเบราว์เซอร์ไปที่ `http://192.168.1.10`

---

## 🎨 4. คู่มือการใช้งานหน้าเว็บทีละขั้นตอน (Step-by-Step UI Manual)

### 🔑 ขั้นตอนที่ 1: การลงทะเบียนและเข้าสู่ระบบ (Authentication)
1. เปิดหน้าเว็บ LUMA บนเบราว์เซอร์
2. หากยังไม่มีบัญชี ให้คลิกปุ่ม **"Register"**
   * กรอก **Username** (ความยาว 3 - 40 ตัวอักษร)
   * กรอก **Password** (ความยาวอย่างน้อย 8 ตัวอักษร)
3. คลิก **"Sign Up"** เมื่อสำเร็จระบบจะล็อกอินให้อัตโนมัติ หรือคลิก **"Login"** เพื่อเข้าสู่ระบบด้วยบัญชีที่มีอยู่
4. เมื่อเข้าสู่ระบบสำเร็จ จะเห็นชื่อผู้ใช้และสถานะการเชื่อมต่อ (Health Badge) มุมบนขวา

---

### 🖼️ ขั้นตอนที่ 2: การสร้างภาพจากข้อความ (Text-to-Image Generation)
1. เลือกแท็บ **"Text to Image"** บนเมนูหลัก
2. **กรอกรายละเอียดคำสั่ง (Prompt Controls):**
   * **Prompt (คำสั่งสร้างภาพ):** ใส่คำอธิบายภาพที่ต้องการ เช่น `a futuristic neon city at night, masterpiece, high resolution`
   * **Negative Prompt (สิ่งที่ไม่อยากให้มี):** เช่น `blurry, low quality, distorted, bad anatomy`
3. **ปรับแต่งค่าทางเทคนิค (Generation Parameters):**
   * **Dimensions (ขนาดภาพ):** เลือกสัดส่วน (เช่น 512x512, 768x768, 512x768) *ระบบจะบังคับให้กว้างxยาวหารด้วย 64 ลงตัว*
   * **Steps (จำนวนขั้นตอนสกัดภาพ):** ปรับระหว่าง 1 - 50 ขั้นตอน (ค่าเริ่มต้น 20)
   * **CFG Scale (ความเข้มงวดทำตาม Prompt):** ปรับระหว่าง 1.0 - 20.0 (ค่าเริ่มต้น 7.0)
   * **Seed:** ใส่ตัวเลขเจาะจง หรือคลิกปุ่ม **"Random Seed"**
4. **เลือกสไตล์สำเร็จรูป (Style Presets):**
   * คลิกเลือกแท็บสไตล์ เช่น *Anime Masterpiece*, *Cyberpunk Neon*, *Cinematic Film*, *Pixel Art* ระบบจะปรับแต่งคำอธิบายให้อัตโนมัติ
5. **กดสร้างภาพ (Generate):**
   * คลิกปุ่ม **"Generate Image"** 
   * ระบบจะแสดงหลอดความคืบหน้า (Progress Bar) สถานะคิว และประมาณเวลาที่เหลือ
6. เมื่อเสร็จสิ้น ภาพจะปรากฏในช่องผลลัพธ์ พร้อมรายละเอียดการเจนภาพ และปุ่ม **"Download Image"**

---

### ✏️ ขั้นตอนที่ 3: การแก้ไขภาพ (Image-to-Image Edit)
1. เลือกแท็บ **"Image Edit"**
2. **อัปโหลดภาพต้นฉบับ:** ดึงไฟล์ภาพมาวางในกล่อง Dropzone หรือคลิกเพื่อเลือกไฟล์ (รองรับ PNG, JPEG, WebP ไม่เกิน 16MB)
3. **กำหนดคำสั่งแก้ไข (Edit Prompt):** ระบุการเปลี่ยนแปลงที่ต้องการ เช่น `change background to a snowy mountain, warm lighting`
4. **ปรับความเข้มการเปลี่ยนภาพ (Denoising Strength):**
   * `0.1 - 0.4`: เปลี่ยนแปลงน้อย ยึดตามโครงเดิม
   * `0.5 - 0.7`: เปลี่ยนแปลงปานกลาง (ค่าแนะนำ 0.65)
   * `0.8 - 1.0`: เปลี่ยนแปลงภาพเดิมเกือบทั้งหมด
5. คลิก **"Apply Image Edit"** แล้วรอระบบประมวลผล

---

### 🧪 ขั้นตอนที่ 4: การใช้งาน 5 อัลกอริทึมประมวลผลภาพ (5 Image Processing Algorithms)
ผู้ใช้สามารถนำภาพเข้าสู่กระบวนการประมวลผลทางดิจิทัลได้ดังนี้:
1. **Grayscale Transform:** คลิกเลือกเมนู `Grayscale` เพื่อแปลงโทนสีตามสูตรความไวแสง ITU-R BT.601
2. **Edge Detection:** คลิกเลือกเมนู `Edge Detection` เพื่อตรวจจับและสกัดเส้นขอบด้วย 3x3 Convolution Filter
3. **Gaussian Blur:** คลิกเลือกเมนู `Gaussian Blur` เพื่อเบลอภาพอย่างนุ่มนวล ลด Noise
4. **Color Inversion:** คลิกเลือกเมนู `Color Inversion` เพื่อสลับเป็นสีตรงข้าม (Negative Color)
5. **Super-Resolution (Upscale):** เลือกเมนู `Upscale 2x/4x` เพื่อขยายขนาดภาพโดยรักษาความคมชัดด้วย Lanczos Windowed Sinc Resampling

---

### 📂 ขั้นตอนที่ 5: การดูประวัติผลงานและการดาวน์โหลด (Job History & Media Download)
1. เลื่อนลงมาที่ส่วน **"My History & Saved Images"**
2. ระบบจะแสดงรายการภาพทั้งหมดที่คุณเคยสร้างไว้
3. คลิกที่รูปภาพเพื่อเปิดดูภาพขนาดเต็ม (Lightbox Display) พร้อมรายละเอียด Seed และพารามิเตอร์ที่ใช้
4. คลิกปุ่ม **"Download"** เพื่อบันทึกภาพลงเครื่องคอมพิวเตอร์ผ่าน Signed Media URL

---

## 🛠️ 5. เครื่องมือและการดูแลรักษาระบบ (DevOps & Operations Utilities)

สำหรับผู้ดูแลระบบ (DevOps/Admin) มีสคริปต์ PowerShell สำเร็จรูปในโฟลเดอร์ `scripts/`:

### 1. สคริปต์สำรองข้อมูลอัตโนมัติ (`scripts/backup.ps1`)
สั่งรันสคริปต์เพื่อบีบอัดฐานข้อมูล SQLite (`luma.db`) และโฟลเดอร์ภาพสื่อ `/media` เป็นไฟล์ ZIP พร้อมลบไฟล์สำรองข้อมูลที่เก่าเกิน 7 วัน:
```powershell
./scripts/backup.ps1
```

### 2. สคริปต์ตรวจสอบสถานะระบบ (`scripts/check-status.ps1`)
ยิงตรวจสอบความพร้อมของ Frontend, Backend และ AI Engine:
```powershell
./scripts/check-status.ps1
```

### 3. สคริปต์ตรวจสอบการเชื่อมต่อเครือข่าย 3 เครื่อง (`scripts/check-network.ps1`)
ตรวจสอบว่า PC 2 ติดต่อ PC 3 ได้ และ PC 3 ติดต่อ PC 1 ผ่านพอร์ต 5000/8000 ได้หรือไม่:
```powershell
./scripts/check-network.ps1 -BackendHost "192.168.1.20" -AiHost "192.168.1.30"
```

---

## ❓ 6. การแก้ไขปัญหาที่พบบ่อย (Troubleshooting & FAQs)

| ปัญหาที่พบ (Issue) | สาเหตุที่เป็นไปได้ (Possible Cause) | แนวทางแก้ไข (Resolution) |
| :--- | :--- | :--- |
| **ขึ้นสถานะ "AI Unavailable" (503)** | AI Engine หรือ Stable Diffusion Forge ล่ม / ไม่ได้เปิด | 1. ตรวจสอบว่า `scripts/run-ai.ps1` หรือ WebUI Forge พอร์ต 7860 เปิดอยู่หรือไม่<br>2. หากไม่มี GPU ระบบจะสลับไปใช้โหมดจำลอง `development-procedural` ให้อัตโนมัติ |
| **ขึ้นข้อผิดพลาด "Unauthorized" (401)** | โทเคน JWT หมดอายุ หรือ `AI_SERVICE_TOKEN` ไม่ตรงกัน | 1. ลองกด Logout แล้วกด Login เข้าสู่ระบบใหม่อีกครั้ง<br>2. ตรวจสอบว่าค่า `AI_SERVICE_TOKEN` ใน `backend/.env` และ `ai-engine/.env` ตรงกัน |
| **ขึ้นข้อผิดพลาด "Dimension must be divisible by 64"** | กำหนดขนาดภาพความกว้างหรือยาวไม่ลงตัว | ปรับขนาดภาพให้เป็นพหุคูณของ 64 เช่น 512, 768, 1024 |
| **อัปโหลดภาพแก้ไขไม่ได้ (413 Payload Too Large)** | ไฟล์ภาพมีขนาดใหญ่เกิน 16MB | บีบอัดไฟล์ภาพหรือแปลงเป็นไฟล์ PNG/JPEG ที่มีขนาดน้อยกว่า 16MB ก่อนอัปโหลด |
| **เบราว์เซอร์ขึ้น 504 Gateway Timeout** | AI Engine ประมวลผลนานเกินไป | ตรวจสอบว่าใน Nginx ตั้งค่า `proxy_read_timeout 190s;` เรียบร้อยแล้ว |

---

**คู่มือฉบับนี้จัดทำขึ้นสำหรับ ProjectLUMA 1.0.0**  
*หากมีข้อสงสัยเพิ่มเติม สามารถตรวจสอบรายละเอียดสัญญา API ได้ใน [docs/API_CONTRACT.md](file:///c:/Users/tten8/Downloads/ProjectLUMA/ProjectLUMA/docs/API_CONTRACT.md)*
