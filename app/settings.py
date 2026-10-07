"""
จัดการการตั้งค่าของร้านที่แอดมินแก้ได้ผ่านเว็บ (เก็บในตาราง settings แบบ key-value)
ค่าเริ่มต้นมาจาก config/env ตอนรันครั้งแรกเท่านั้น หลังจากนั้นใช้ค่าในฐานข้อมูล
"""
from flask import g, current_app
from app import db

# รายการ setting ทั้งหมด: key -> (ชื่อที่แสดงให้แอดมิน, เป็นข้อความยาวหรือไม่)
SETTING_FIELDS = [
    ("store_name", "ชื่อร้าน", False),
    ("store_phone", "เบอร์โทรติดต่อร้าน", False),
    ("store_address", "ที่อยู่ร้าน", True),
    ("store_hours", "เวลาทำการ", False),
    ("checkout_message", "ข้อความแจ้งหลังสั่งซื้อ", True),
    ("preorder_message", "ข้อความแจ้งหลังสั่งจองพรีออเดอร์", True),
    ("theme_color", "สีหลักของเว็บ", False),
]


def _defaults():
    """ค่าเริ่มต้นจาก config/env"""
    return {
        "store_name": current_app.config.get("STORE_NAME", "ร้านขายยาออนไลน์"),
        "store_phone": current_app.config.get("STORE_PHONE", "02-000-0000"),
        "store_address": "",
        "store_hours": "",
        "checkout_message": "กรุณาติดต่อชำระเงินที่ร้าน",
        "preorder_message": "ทางร้านจะติดต่อกลับตามเบอร์โทรที่คุณลงทะเบียนไว้",
        "theme_color": "#ee4d2d",
        "logo_url": "",
    }


def ensure_defaults():
    """ใส่ค่าเริ่มต้นลงฐานข้อมูลถ้ายังไม่มี (เรียกตอนแอปเริ่มทำงาน)"""
    defaults = _defaults()
    for key, val in defaults.items():
        db.query(
            "INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
            (key, val),
        )


def get_all():
    """ดึงการตั้งค่าทั้งหมดเป็น dict (cache ต่อ request ใน g)"""
    if "settings" in g:
        return g.settings
    rows = db.query("SELECT key, value FROM settings", fetchall=True) or []
    data = _defaults()
    data.update({r["key"]: r["value"] for r in rows})
    g.settings = data
    return data


def get(key, default=""):
    return get_all().get(key, default)


def update(values):
    """อัปเดตหลาย setting พร้อมกัน (values เป็น dict key->value)"""
    for key, val in values.items():
        db.query(
            "INSERT INTO settings (key, value) VALUES (%s, %s) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            (key, val or ""),
        )
    g.pop("settings", None)  # ล้าง cache เพื่อให้ดึงค่าใหม่
