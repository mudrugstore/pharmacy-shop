"""อัปโหลดรูปสินค้าไปที่ Supabase Storage (ผ่าน REST API) พร้อมบีบอัดรูปก่อนอัปโหลด"""
import io
import uuid
import requests
from PIL import Image
from flask import current_app


def _config():
    return (
        current_app.config["SUPABASE_URL"].rstrip("/"),
        current_app.config["SUPABASE_SERVICE_KEY"],
        current_app.config["SUPABASE_BUCKET"],
    )


def compress_image(file_storage, max_size=800, quality=80):
    """
    ย่อ/บีบอัดรูปให้ด้านยาวสุดไม่เกิน max_size px แล้วแปลงเป็น JPEG
    คืนค่าเป็น bytes พร้อมอัปโหลด
    """
    img = Image.open(file_storage.stream)
    # แปลงเป็น RGB เผื่อเป็น PNG โปร่งใส/โหมดอื่น
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.thumbnail((max_size, max_size))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    buf.seek(0)
    return buf.read()


def _upload(file_storage, max_size):
    """
    บีบรูปแล้วอัปโหลดไป Supabase Storage คืน public URL
    ถ้ายังไม่ได้ตั้งค่า Supabase Storage จะคืน None (เว็บยังทำงานได้ แค่ไม่มีรูป)
    """
    supabase_url, service_key, bucket = _config()
    if not supabase_url or not service_key:
        return None

    data = compress_image(file_storage, max_size=max_size)
    filename = f"{uuid.uuid4().hex}.jpg"
    upload_endpoint = f"{supabase_url}/storage/v1/object/{bucket}/{filename}"

    # ส่งทั้ง Authorization และ apikey เพื่อรองรับ key ทั้งแบบเดิม (service_role JWT)
    # และแบบใหม่ของ Supabase (sb_secret_...) ซึ่งบาง endpoint ต้องการ header apikey ด้วย
    resp = requests.post(
        upload_endpoint,
        headers={
            "Authorization": f"Bearer {service_key}",
            "apikey": service_key,
            "Content-Type": "image/jpeg",
            "x-upsert": "true",
        },
        data=data,
        timeout=30,
    )
    # ถ้าไม่สำเร็จ แสดงข้อความจริงจาก Supabase (ช่วยวินิจฉัย เช่น bucket not found, invalid jwt)
    if resp.status_code >= 400:
        raise RuntimeError(
            f"Supabase storage ตอบ {resp.status_code}: {resp.text[:300]} "
            f"(endpoint: {upload_endpoint})"
        )

    # public URL (bucket ต้องตั้งเป็น public ใน Supabase)
    return f"{supabase_url}/storage/v1/object/public/{bucket}/{filename}"


def upload_product_image(file_storage):
    """อัปโหลดรูปสินค้า (ย่อด้านยาวสุดไม่เกิน 600px เพียงพอกับการ์ด/หน้ารายละเอียด ประหยัดแบนด์วิดท์)"""
    return _upload(file_storage, max_size=600)


def upload_banner_image(file_storage):
    """อัปโหลดรูปแบนเนอร์ (แนวนอน ย่อด้านยาวสุดไม่เกิน 1600px เพื่อคงความคม)"""
    return _upload(file_storage, max_size=1600)
