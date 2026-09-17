# เลือกอิมเมจพื้นฐานของบริการ
FROM nginx:1.27-alpine

# คัดลอกหน้าเว็บสถิตไปยังโฟลเดอร์ที่ Nginx ให้บริการ

COPY frontend/ /usr/share/nginx/html/
# ติดตั้งเส้นทาง proxy ที่ใช้ชื่อบริการภายในเครือข่าย Compose
COPY nginx/docker.conf /etc/nginx/conf.d/default.conf

# ระบุพอร์ตของบริการ การเปิดออกเครื่อง host ต้องกำหนดเพิ่มตอนรัน

EXPOSE 80
# ตรวจว่าเว็บในคอนเทนเนอร์ตอบคำขอได้
HEALTHCHECK --interval=15s --timeout=3s --retries=3 CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1

