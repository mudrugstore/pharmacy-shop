"""App factory ของเว็บร้านขายยาออนไลน์"""
from datetime import timezone, timedelta
from flask import Flask, request
from werkzeug.security import generate_password_hash
from config import Config
from app import db

# เขตเวลาประเทศไทย (UTC+7)
THAI_TZ = timezone(timedelta(hours=7))


def to_thai_time(value, fmt="%d/%m/%Y %H:%M"):
    """แปลง datetime (เก็บเป็น UTC) เป็นเวลาประเทศไทยแล้ว format เป็นข้อความ"""
    if value is None:
        return ""
    # ถ้าไม่มี tzinfo ให้ถือว่าเป็น UTC (ค่าจาก Postgres TIMESTAMPTZ จะมี tz อยู่แล้ว)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(THAI_TZ).strftime(fmt)


def money(value):
    """
    format ตัวเลขเงินให้มีเครื่องหมายคั่นหลักพันและทศนิยม 2 ตำแหน่ง
    เช่น 1350 -> '1,350.00', 1234.5 -> '1,234.50'
    """
    try:
        return "{:,.2f}".format(float(value or 0))
    except (TypeError, ValueError):
        return "0.00"


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # เชื่อมต่อฐานข้อมูล + สร้างตาราง + เตรียมบัญชีแอดมิน
    db.init_pool(app.config["DATABASE_URL"])
    with app.app_context():
        db.init_schema()
        _ensure_admin(app)
        from app import settings
        settings.ensure_defaults()

    # ลงทะเบียน blueprints
    from app.routes.auth import bp as auth_bp
    from app.routes.shop import bp as shop_bp
    from app.routes.preorder import bp as preorder_bp
    from app.routes.admin import bp as admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(shop_bp)
    app.register_blueprint(preorder_bp)
    app.register_blueprint(admin_bp)

    # ให้ browser cache ไฟล์ static (CSS/JS) ได้นานขึ้น ลดการโหลดซ้ำทุกหน้า
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 60 * 60 * 24 * 7  # 7 วัน

    # ปิด DB connection ตอนจบแต่ละ request (reuse connection เดียวต่อ request เพื่อ performance)
    app.teardown_appcontext(db.close_request_conn)

    # บีบอัด response ด้วย gzip (ลดขนาด HTML/CSS/JSON ที่ส่ง ~60-70% หน้าโหลดเร็วขึ้นบนมือถือ)
    import gzip as _gzip

    @app.after_request
    def _compress(response):
        accept = request.headers.get("Accept-Encoding", "")
        if "gzip" not in accept.lower():
            return response
        # บีบเฉพาะ text ที่ใหญ่พอ และยังไม่ถูกบีบ
        ctype = response.content_type or ""
        compressible = ctype.startswith(("text/", "application/json", "application/javascript")) or "javascript" in ctype
        if (not compressible or response.direct_passthrough
                or response.status_code < 200 or response.status_code >= 300
                or "Content-Encoding" in response.headers):
            return response
        data = response.get_data()
        if len(data) < 500:   # ไฟล์เล็กไม่คุ้มบีบ
            return response
        response.set_data(_gzip.compress(data, 6))
        response.headers["Content-Encoding"] = "gzip"
        response.headers["Vary"] = "Accept-Encoding"
        response.headers["Content-Length"] = len(response.get_data())
        return response

    # Jinja filter แปลงเวลาเป็นเวลาไทย เรียกใช้ใน template ว่า {{ dt|thaidt }}
    app.jinja_env.filters["thaidt"] = to_thai_time
    # Jinja filter format เงินมีเครื่องหมายคั่นหลักพัน เรียกใช้ว่า {{ price|money }}
    app.jinja_env.filters["money"] = money

    # ให้ template เข้าถึงข้อมูล user และข้อมูลร้านได้ทุกหน้า
    from app.auth_utils import get_current_user
    from app import settings

    @app.context_processor
    def inject_globals():
        # AJAX ที่คืน partial (เช่น เปลี่ยนหมวดหมู่) ไม่ต้องใช้ badge/cart_count
        # -> ข้าม query ของ _nav_badges เพื่อลดภาระ DB ต่อ request (settings มี cache อยู่แล้ว)
        is_ajax = request.headers.get("X-Requested-With") == "fetch"
        s = settings.get_all()
        user = get_current_user()
        return {
            "current_user": user,
            "store_name": s["store_name"],
            "store_phone": s["store_phone"],
            "store_address": s["store_address"],
            "store_hours": s["store_hours"],
            "checkout_message": s["checkout_message"],
            "preorder_message": s["preorder_message"],
            "theme_color": s.get("theme_color") or "#ee4d2d",
            "logo_url": s.get("logo_url") or "",
            "supabase_url": app.config.get("SUPABASE_URL") or "",
            "cart_count": _cart_count(),
            "nav_badges": {} if is_ajax else _nav_badges(user),
        }

    return app


def _nav_badges(user):
    """
    badge แจ้งเตือนสำหรับเมนู (จุดแดง มี/ไม่มี) — ใช้ EXISTS เร็วกว่า COUNT
    เพราะ DB หยุดค้นทันทีที่เจอแถวแรก (query เดียวต่อ request เฉพาะเมื่อ login)
    """
    from app import db
    badges = {"admin_orders": False, "admin_preorders": False,
              "my_orders": False, "my_preorders": False}
    if not user:
        return badges
    try:
        if user["is_admin"]:
            row = db.query(
                "SELECT "
                "EXISTS(SELECT 1 FROM orders WHERE status = 'รอดำเนินการ') AS o, "
                "EXISTS(SELECT 1 FROM preorder_requests WHERE status = 'รอติดต่อกลับ') AS p",
                fetchone=True,
            )
            badges["admin_orders"] = row["o"]
            badges["admin_preorders"] = row["p"]
        else:
            row = db.query(
                "SELECT "
                "EXISTS(SELECT 1 FROM orders WHERE user_id = %s AND seen_by_user = FALSE) AS o, "
                "EXISTS(SELECT 1 FROM preorder_requests WHERE user_id = %s AND seen_by_user = FALSE) AS p",
                (user["id"], user["id"]),
                fetchone=True,
            )
            badges["my_orders"] = row["o"]
            badges["my_preorders"] = row["p"]
    except Exception:
        pass  # กันกรณี DB มีปัญหาชั่วคราว ไม่ให้ทั้งหน้าพัง
    return badges


def _cart_count():
    """นับจำนวนชิ้นในตะกร้าเพื่อแสดงบน navbar"""
    from flask import session
    cart = session.get("cart", {})
    return sum(cart.values()) if cart else 0


def _ensure_admin(app):
    """สร้างบัญชีแอดมินจาก env ถ้ายังไม่มี หรืออัปเกรดบัญชีเดิมให้เป็นแอดมิน"""
    phone = app.config["ADMIN_PHONE"]
    existing = db.query("SELECT id FROM users WHERE phone = %s", (phone,), fetchone=True)
    if existing:
        db.query("UPDATE users SET is_admin = TRUE WHERE phone = %s", (phone,), commit=True)
    else:
        db.query(
            """INSERT INTO users (name, phone, password_hash, is_admin)
               VALUES (%s, %s, %s, TRUE)""",
            (
                app.config["ADMIN_NAME"],
                phone,
                generate_password_hash(app.config["ADMIN_PASSWORD"]),
            ),
            commit=True,
        )
