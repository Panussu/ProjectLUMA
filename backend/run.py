# โหลด .env และเริ่ม Flask แบบ debug หรือ Waitress ตามค่ากำหนด
import os

from dotenv import load_dotenv
from waitress import serve

from luma_backend import create_app

# โหลดค่าจาก .env ก่อนสร้างแอปหรืออ่าน environment

load_dotenv()
app = create_app()

# เริ่มบริการหรือคำสั่งเฉพาะเมื่อรันไฟล์นี้โดยตรง

if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    # เลือก development server เฉพาะ debug มิฉะนั้นใช้ Waitress
    if os.getenv("FLASK_DEBUG", "0") == "1":
        app.run(host=host, port=port, debug=True)
    else:
        serve(app, host=host, port=port, threads=int(os.getenv("WEB_THREADS", "8")))

