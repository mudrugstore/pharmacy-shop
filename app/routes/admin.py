"""ฝั่งแอดมิน: จัดการหมวดหมู่ สินค้า สต็อก พรีออเดอร์ ออเดอร์ และผู้ใช้"""
from decimal import Decimal, InvalidOperation
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash,
)
from app import db
from app import settings as app_settings
from app import cache
from app.storage import upload_product_image, upload_banner_image
from app.auth_utils import admin_required

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.after_request
def _clear_cache_after_mutation(response):
    """
    หลังจาก admin ทำ POST (เพิ่ม/แก้/ลบ หมวดหมู่/สินค้า/แบนเนอร์/ตั้งค่า)
    ล้าง cache ทั้งหมดเพื่อให้ฝั่งลูกค้าเห็นข้อมูลใหม่ทันที (ไม่ต้องรอ TTL หมด)
    """
    if request.method == "POST":
        cache.invalidate()
    return response


@bp.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    """หน้าตั้งค่าร้าน: แอดมินแก้ชื่อร้าน เบอร์โทร ข้อความต่างๆ ได้เอง"""
    if request.method == "POST":
        values = {}
        for key, _label, _is_long in app_settings.SETTING_FIELDS:
            values[key] = (request.form.get(key) or "").strip()
        if not values.get("store_name"):
            flash("กรุณากรอกชื่อร้าน", "danger")
            return redirect(url_for("admin.settings"))

        # อัปโหลดโลโก้ถ้ามีการเลือกไฟล์ใหม่
        file = request.files.get("logo")
        if file and file.filename:
            try:
                logo_url = upload_product_image(file)
                if logo_url:
                    values["logo_url"] = logo_url
            except Exception as e:
                flash(f"อัปโหลดโลโก้ไม่สำเร็จ: {e}", "danger")
                return redirect(url_for("admin.settings"))

        app_settings.update(values)
        flash("บันทึกการตั้งค่าร้านแล้ว", "success")
        return redirect(url_for("admin.settings"))

    current = app_settings.get_all()
    return render_template(
        "admin/settings.html",
        fields=app_settings.SETTING_FIELDS,
        current=current,
    )


@bp.route("/")
@admin_required
def dashboard():
    stats = {
        "products": db.query("SELECT COUNT(*) AS c FROM products", fetchone=True)["c"],
        "categories": db.query("SELECT COUNT(*) AS c FROM categories", fetchone=True)["c"],
        "orders": db.query("SELECT COUNT(*) AS c FROM orders", fetchone=True)["c"],
        "preorders": db.query(
            "SELECT COUNT(*) AS c FROM preorder_requests WHERE status = 'รอติดต่อกลับ'",
            fetchone=True,
        )["c"],
        "users": db.query("SELECT COUNT(*) AS c FROM users WHERE is_admin = FALSE", fetchone=True)["c"],
    }
    return render_template("admin/dashboard.html", stats=stats)


# ---------- หมวดหมู่ ----------
@bp.route("/categories", methods=["GET", "POST"])
@admin_required
def categories():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("กรุณากรอกชื่อหมวดหมู่", "danger")
            return redirect(url_for("admin.categories"))
        # อัปโหลดรูปหมวดหมู่ถ้ามี
        image_url = ""
        file = request.files.get("image")
        if file and file.filename:
            try:
                image_url = upload_product_image(file) or ""
            except Exception as e:
                flash(f"อัปโหลดรูปไม่สำเร็จ: {e}", "danger")
                return redirect(url_for("admin.categories"))
        db.query(
            "INSERT INTO categories (name, image_url) VALUES (%s, %s)",
            (name, image_url),
            commit=True,
        )
        flash("เพิ่มหมวดหมู่แล้ว", "success")
        return redirect(url_for("admin.categories"))

    rows = db.query(
        """SELECT c.id, c.name, c.image_url, COUNT(p.id) AS product_count
           FROM categories c LEFT JOIN products p ON p.category_id = c.id
           GROUP BY c.id, c.name, c.image_url ORDER BY c.name""",
        fetchall=True,
    )
    return render_template("admin/categories.html", categories=rows)


@bp.route("/categories/delete/<int:category_id>", methods=["POST"])
@admin_required
def delete_category(category_id):
    db.query("DELETE FROM categories WHERE id = %s", (category_id,), commit=True)
    flash("ลบหมวดหมู่แล้ว (สินค้าในหมวดนี้จะไม่มีหมวดหมู่)", "info")
    return redirect(url_for("admin.categories"))


# ---------- สินค้า ----------
@bp.route("/products")
@admin_required
def products():
    rows = db.query(
        """SELECT p.id, p.name, p.price, p.stock, p.is_preorder, p.image_url,
                  c.name AS category_name
           FROM products p LEFT JOIN categories c ON p.category_id = c.id
           ORDER BY p.created_at DESC""",
        fetchall=True,
    )
    return render_template("admin/products.html", products=rows)


@bp.route("/products/new", methods=["GET", "POST"])
@admin_required
def new_product():
    categories = db.query("SELECT id, name FROM categories ORDER BY name", fetchall=True)
    if request.method == "POST":
        result = _save_product_form(None)
        if result is True:
            flash("เพิ่มสินค้าแล้ว", "success")
            return redirect(url_for("admin.products"))
        flash(result, "danger")
    return render_template("admin/product_form.html", categories=categories, product=None)


@bp.route("/products/edit/<int:product_id>", methods=["GET", "POST"])
@admin_required
def edit_product(product_id):
    product = db.query("SELECT * FROM products WHERE id = %s", (product_id,), fetchone=True)
    if not product:
        flash("ไม่พบสินค้านี้", "danger")
        return redirect(url_for("admin.products"))
    categories = db.query("SELECT id, name FROM categories ORDER BY name", fetchall=True)

    if request.method == "POST":
        result = _save_product_form(product_id)
        if result is True:
            flash("บันทึกการแก้ไขแล้ว", "success")
            return redirect(url_for("admin.products"))
        flash(result, "danger")
        product = db.query("SELECT * FROM products WHERE id = %s", (product_id,), fetchone=True)

    return render_template("admin/product_form.html", categories=categories, product=product)


def _save_product_form(product_id):
    """
    บันทึกฟอร์มสินค้า (ใช้ร่วมกันทั้งเพิ่มและแก้ไข)
    คืน True ถ้าสำเร็จ หรือข้อความ error ถ้าไม่สำเร็จ
    """
    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip()
    price_raw = request.form.get("price") or "0"
    stock = request.form.get("stock", type=int) or 0
    category_id = request.form.get("category_id", type=int)
    is_preorder = request.form.get("is_preorder") == "on"
    badge_text = (request.form.get("badge_text") or "").strip()[:20]  # จำกัดความยาวป้าย

    if not name:
        return "กรุณากรอกชื่อสินค้า"
    try:
        price = Decimal(price_raw)
        if price < 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        return "ราคาไม่ถูกต้อง"

    # อัปโหลดรูปถ้ามี
    image_url = None
    file = request.files.get("image")
    if file and file.filename:
        try:
            image_url = upload_product_image(file)
        except Exception as e:
            return f"อัปโหลดรูปไม่สำเร็จ: {e}"

    if product_id is None:
        db.query(
            """INSERT INTO products
               (category_id, name, description, price, stock, image_url, is_preorder, badge_text)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (category_id, name, description, price, stock, image_url or "", is_preorder, badge_text),
            commit=True,
        )
    else:
        if image_url is not None:
            db.query(
                """UPDATE products SET category_id=%s, name=%s, description=%s,
                   price=%s, stock=%s, image_url=%s, is_preorder=%s, badge_text=%s WHERE id=%s""",
                (category_id, name, description, price, stock, image_url, is_preorder, badge_text, product_id),
                commit=True,
            )
        else:
            db.query(
                """UPDATE products SET category_id=%s, name=%s, description=%s,
                   price=%s, stock=%s, is_preorder=%s, badge_text=%s WHERE id=%s""",
                (category_id, name, description, price, stock, is_preorder, badge_text, product_id),
                commit=True,
            )
    return True


@bp.route("/products/stock/<int:product_id>", methods=["POST"])
@admin_required
def update_stock(product_id):
    stock = request.form.get("stock", type=int)
    if stock is not None and stock >= 0:
        db.query("UPDATE products SET stock = %s WHERE id = %s", (stock, product_id), commit=True)
        flash("อัปเดตสต็อกแล้ว", "success")
    else:
        flash("จำนวนสต็อกไม่ถูกต้อง", "danger")
    return redirect(url_for("admin.products"))


@bp.route("/products/delete/<int:product_id>", methods=["POST"])
@admin_required
def delete_product(product_id):
    db.query("DELETE FROM products WHERE id = %s", (product_id,), commit=True)
    flash("ลบสินค้าแล้ว", "info")
    return redirect(url_for("admin.products"))


# ---------- ออเดอร์ ----------
@bp.route("/orders")
@admin_required
def orders():
    rows = db.query(
        """SELECT o.id, o.total, o.status, o.created_at, u.name AS customer_name, u.phone
           FROM orders o JOIN users u ON o.user_id = u.id
           ORDER BY o.created_at DESC""",
        fetchall=True,
    )
    return render_template("admin/orders.html", orders=rows)


@bp.route("/orders/<int:order_id>", methods=["GET", "POST"])
@admin_required
def order_detail(order_id):
    if request.method == "POST":
        status = (request.form.get("status") or "").strip()
        if status:
            db.query("UPDATE orders SET status = %s WHERE id = %s", (status, order_id), commit=True)
            flash("อัปเดตสถานะคำสั่งซื้อแล้ว", "success")
        return redirect(url_for("admin.order_detail", order_id=order_id))

    order = db.query(
        """SELECT o.id, o.total, o.status, o.note, o.created_at,
                  u.name AS customer_name, u.phone
           FROM orders o JOIN users u ON o.user_id = u.id
           WHERE o.id = %s""",
        (order_id,),
        fetchone=True,
    )
    if not order:
        flash("ไม่พบคำสั่งซื้อนี้", "danger")
        return redirect(url_for("admin.orders"))
    items = db.query(
        "SELECT product_name, unit_price, quantity FROM order_items WHERE order_id = %s",
        (order_id,),
        fetchall=True,
    )
    return render_template("admin/order_detail.html", order=order, items=items)


# ---------- พรีออเดอร์ ----------
@bp.route("/preorders", methods=["GET", "POST"])
@admin_required
def preorders():
    rows = db.query(
        """SELECT pr.id, pr.product_name, pr.quantity, pr.status, pr.created_at,
                  u.name AS customer_name, u.phone
           FROM preorder_requests pr JOIN users u ON pr.user_id = u.id
           ORDER BY pr.created_at DESC""",
        fetchall=True,
    )
    return render_template("admin/preorders.html", preorders=rows)


@bp.route("/preorders/status/<int:request_id>", methods=["POST"])
@admin_required
def preorder_status(request_id):
    status = (request.form.get("status") or "").strip()
    if status:
        db.query(
            "UPDATE preorder_requests SET status = %s WHERE id = %s",
            (status, request_id),
            commit=True,
        )
        flash("อัปเดตสถานะพรีออเดอร์แล้ว", "success")
    return redirect(url_for("admin.preorders"))


# ---------- จัดการผู้ใช้ ----------
@bp.route("/users")
@admin_required
def users():
    rows = db.query(
        """SELECT id, name, phone, must_reset_password, created_at
           FROM users WHERE is_admin = FALSE ORDER BY created_at DESC""",
        fetchall=True,
    )
    return render_template("admin/users.html", users=rows)


@bp.route("/users/reset/<int:user_id>", methods=["POST"])
@admin_required
def reset_user_password(user_id):
    """ปลดล็อกให้ user ตั้งรหัสใหม่เอง (ตั้ง must_reset_password = TRUE)"""
    db.query(
        "UPDATE users SET must_reset_password = TRUE WHERE id = %s AND is_admin = FALSE",
        (user_id,),
        commit=True,
    )
    flash("รีเซ็ตรหัสผ่านแล้ว ผู้ใช้จะต้องตั้งรหัสใหม่เมื่อเข้าสู่ระบบครั้งถัดไป", "success")
    return redirect(url_for("admin.users"))


@bp.route("/users/delete/<int:user_id>", methods=["POST"])
@admin_required
def delete_user(user_id):
    db.query("DELETE FROM users WHERE id = %s AND is_admin = FALSE", (user_id,), commit=True)
    flash("ลบผู้ใช้แล้ว", "info")
    return redirect(url_for("admin.users"))


# ---------- แบนเนอร์โฆษณา ----------
@bp.route("/banners", methods=["GET", "POST"])
@admin_required
def banners():
    """จัดการแบนเนอร์โฆษณาบนหน้าร้าน: อัปโหลดรูป + ลิงก์ + ลำดับ"""
    if request.method == "POST":
        file = request.files.get("image")
        link_url = (request.form.get("link_url") or "").strip()
        sort_order = request.form.get("sort_order", type=int) or 0
        display_page = (request.form.get("display_page") or "both").strip()
        if display_page not in ("shop", "preorder", "both"):
            display_page = "both"
        if not file or not file.filename:
            flash("กรุณาเลือกรูปแบนเนอร์", "danger")
            return redirect(url_for("admin.banners"))
        try:
            image_url = upload_banner_image(file)
        except Exception as e:
            flash(f"อัปโหลดรูปไม่สำเร็จ: {e}", "danger")
            return redirect(url_for("admin.banners"))
        if not image_url:
            flash("ยังไม่ได้ตั้งค่า Supabase Storage จึงอัปโหลดรูปไม่ได้", "danger")
            return redirect(url_for("admin.banners"))
        db.query(
            "INSERT INTO banners (image_url, link_url, sort_order, display_page) VALUES (%s, %s, %s, %s)",
            (image_url, link_url, sort_order, display_page),
            commit=True,
        )
        flash("เพิ่มแบนเนอร์แล้ว", "success")
        return redirect(url_for("admin.banners"))

    rows = db.query(
        "SELECT id, image_url, link_url, sort_order, is_active, display_page FROM banners ORDER BY sort_order, id",
        fetchall=True,
    )
    return render_template("admin/banners.html", banners=rows)


@bp.route("/banners/toggle/<int:banner_id>", methods=["POST"])
@admin_required
def toggle_banner(banner_id):
    """เปิด/ปิดการแสดงแบนเนอร์"""
    db.query(
        "UPDATE banners SET is_active = NOT is_active WHERE id = %s",
        (banner_id,),
        commit=True,
    )
    flash("อัปเดตสถานะแบนเนอร์แล้ว", "success")
    return redirect(url_for("admin.banners"))


@bp.route("/banners/delete/<int:banner_id>", methods=["POST"])
@admin_required
def delete_banner(banner_id):
    db.query("DELETE FROM banners WHERE id = %s", (banner_id,), commit=True)
    flash("ลบแบนเนอร์แล้ว", "info")
    return redirect(url_for("admin.banners"))

