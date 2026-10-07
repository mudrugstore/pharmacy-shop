"""การตั้งค่าทั้งหมดของแอป อ่านค่าจาก environment variables"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    # ฐานข้อมูล Supabase (PostgreSQL)
    DATABASE_URL = os.environ.get("DATABASE_URL", "")

    # Supabase Storage สำหรับเก็บรูปสินค้า
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
    SUPABASE_BUCKET = os.environ.get("SUPABASE_BUCKET", "product-images")

    # บัญชีแอดมินเริ่มต้น
    ADMIN_PHONE = os.environ.get("ADMIN_PHONE", "0800000000")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme123")
    ADMIN_NAME = os.environ.get("ADMIN_NAME", "ผู้ดูแลระบบ")

    # ข้อมูลร้าน
    STORE_NAME = os.environ.get("STORE_NAME", "ร้านขายยาออนไลน์")
    STORE_PHONE = os.environ.get("STORE_PHONE", "02-000-0000")

    # จำกัดขนาดไฟล์อัปโหลด 5 MB
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
