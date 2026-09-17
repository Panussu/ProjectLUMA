# เลือกอิมเมจพื้นฐานของบริการ
FROM python:3.12-slim

# กำหนดสภาพแวดล้อมของโปรเซสภายในคอนเทนเนอร์

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# โฟลเดอร์ทำงานภายในอิมเมจ
WORKDIR /app

# คัดลอกรายการไลบรารีก่อนเพื่อใช้แคชขั้นติดตั้ง

COPY requirements.txt .
# ติดตั้งไลบรารีที่บริการต้องใช้โดยไม่เก็บแคช pip
RUN pip install --no-cache-dir -r requirements.txt
# คัดลอกโค้ดบริการโดยใช้รายการยกเว้นของ Docker build context
COPY . .

# ระบุพอร์ตของบริการ การเปิดออกเครื่อง host ต้องกำหนดเพิ่มตอนรัน

EXPOSE 8000
# คำสั่งเริ่มบริการเมื่อรันคอนเทนเนอร์
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

