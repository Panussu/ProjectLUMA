# 📋 แผนการทดสอบและเกณฑ์การยอมรับระบบ (ProjectLUMA Master Test Plan)

---

## 🤖 1. การตรวจสอบอัตโนมัติ (Automated Checks)

สามารถสั่งรันชุดทดสอบอัตโนมัติทั้งหมดจากโฟลเดอร์หลักผ่านสคริปต์ PowerShell:

```powershell
./scripts/run-all-tests.ps1
```

หรือรันผ่านคำสั่งย่อย:

```powershell
python -m venv backend/.venv
./backend/.venv/Scripts/pip.exe install -r requirements-dev.txt
./backend/.venv/Scripts/python.exe -m pytest --tb=short
node --check frontend/assets/app.js
docker compose config --quiet
```

### ขอบเขตการทดสอบอัตโนมัติ (Automated Test Coverage)
ชุดทดสอบอัตโนมัติครอบคลุม:
* ระบบการยืนยันตัวตนและการเข้าสู่ระบบด้วย JWT
* การแยกข้อมูลและสิทธิ์ของผู้ใช้งานแต่ละคน (User Data Isolation)
* การตรวจสอบความถูกต้องของพารามิเตอร์ (Request Validation - กว้าง/ยาว ต้องหารด้วย 64 ลงตัว)
* การประมวลผลงานสร้างภาพ (Text-to-Image) และแก้ไขภาพ (Image-to-Image)
* การยืนยันตัวตนระดับบริการภายใน (Private AI Service Token Security)
* สถานะงานคงค้างและการโหลดสื่อผ่าน Signed Media Link
* การจำลองผลลัพธ์คงที่ (Deterministic Development Provider Output)

---

## 🎨 2. รายการตรวจเช็กหน้าจอเบราว์เซอร์ (Manual Browser Checklist)

- [x] โครงสร้างหน้าเว็บรองรับทั้งขนาดหน้าจอ Desktop, Tablet และ Mobile (Responsive Layout)
- [x] ปุ่มกด ฟอร์ม แท็บเมนู และกล่องควบคุมสามารถเข้าถึงได้ผ่านปุ่ม `Tab` (Keyboard Focus & Accessibility)
- [x] แสดงข้อความแจ้งเตือนเมื่อลงทะเบียนหรือเข้าสู่ระบบไม่สำเร็จอย่างชัดเจน
- [x] แสดงสถานะกำลังประมวลผล (Queued / Processing Spinner & Progress Bar) ขณะรอผลลัพธ์ภาพ
- [x] อัปโหลดไฟล์ภาพแก้ไขรองรับประเภท PNG, JPEG, WebP และปฏิเสธไฟล์ที่มีขนาดใหญ่เกิน 16MB
- [x] การกด Refresh หน้าเว็บไม่ทำให้สิทธิ์การเข้าสู่ระบบหลุด จนกว่าจะหมดอายุ JWT หรือกด Logout
- [x] บัญชีผู้ใช้ A ไม่สามารถมองเห็นหรือดาวน์โหลดงานของผู้ใช้ B ได้ (User Data Isolation Boundary)
- [x] เมื่อ AI Engine หรือ WebUI Forge ขัดข้อง หน้าเว็บแสดงสถานะ "AI Unavailable" ใน Health Badge โดยไม่ crash
- [x] สามารถคลิกปุ่มดาวน์โหลดเพื่อบันทึกไฟล์ภาพผลลัพธ์ PNG ลงเครื่องคอมพิวเตอร์ได้สมบูรณ์

---

## 🌐 3. เกณฑ์การยอมรับการทดสอบแบบ 3 เครื่องบนวง VLAN (3-PC Same-VLAN Acceptance Test)

ก่อนทำการทดสอบ ให้บันทึก IPv4 Address จริงจากคำสั่ง `ipconfig` ของแต่ละเครื่อง ยืนยันว่า PC 2 สามารถสื่อสารกับ Flask บน PC 3 ได้ และ PC 3 สามารถสื่อสารกับ FastAPI บน PC 1 ได้:

```powershell
# รันที่ PC 2
Test-NetConnection 192.168.1.20 -Port 5000

# รันที่ PC 3
Test-NetConnection 192.168.1.30 -Port 8000
```

| รายการตรวจ | ผลลัพธ์ที่คาดหมาย |
| --- | --- |
| เบราว์เซอร์เปิด `192.168.1.10` | Nginx ให้บริการหน้าเว็บ LUMA สวยงาม |
| เบราว์เซอร์เรียก `/api/v1/health` | Nginx ส่งต่อคำขอไปยัง Flask บน PC 3 |
| Flask เรียก FastAPI ที่ `192.168.1.30:8000/health` | บริการ AI รายงานสถานะ `ok` |
| คำขอสร้างภาพ (Generate) | ส่งตอบ HTTP 202 ตามด้วยสถานะงานเสร็จสิ้นและแสดงภาพ |
| คำขอแก้ไขภาพ (Edit) | ไฟล์อัปโหลดส่งถึง Flask แล้วส่งต่อไปยังเครื่อง AI บน PC 1 |
| คำขอผลลัพธ์ (Result) | Signed `/media` URL ส่งคืนไฟล์ภาพ PNG สมบูรณ์ |
| เมื่อเครื่อง AI หยุดทำงาน | Backend ยังคงทำงานได้และรายงานสถานะ AI unavailable |
| โทเคนบริการไม่ถูกต้อง | บริการ AI ส่งคืน HTTP 401 Unauthorized |
| เมื่อเครื่อง Backend หยุดทำงาน | Nginx ส่งคืน Gateway Error โดยไฟล์ Frontend ยังโหลดได้ |

*บันทึกชื่อ VLAN, IP จริง, วันที่ทดสอบ, ผู้ทดสอบ และหลักฐานการทดสอบใน [docs/PROJECTLUMA_3PC_TEST_GUIDE.md](file:///c:/Users/tten8/Downloads/ProjectLUMA/ProjectLUMA/docs/PROJECTLUMA_3PC_TEST_GUIDE.md) ก่อนการสาธิต*
