"""ฝั่งลูกค้า: เมนูพรีออเดอร์ (สินค้าที่แอดมินเปิดให้สั่งจอง)"""
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash,
)
from app import db
from app.auth_utils import login_required, get_current_user

bp = Blueprint("preorder", __name__, url_prefix="/preorder")


@bp.route("/")
def index():
    """แสดงสินค้าที่เปิดให้พรีออเดอร์ (is_preorder = TRUE)"""
    products = db.query(
        """SELECT id, name, description, price, image_url
           FROM products
           WHERE is_active = TRUE AND is_preorder = TRUE
           ORDER BY name""",
        fetchall=True,
    )
    # แบนเนอร์ที่ตั้งให้แสดงหน้าพรีออเดอร์ ('preorder') หรือทั้งสอง ('both')
    banners = db.query(
        "SELECT image_url, link_url FROM banners "
        "WHERE is_active = TRUE AND display_page IN ('preorder', 'both') "
        "ORDER BY sort_order, id",
        fetchall=True,
    )
    return render_template("preorder/index.html", products=products, banners=banners)


@bp.route("/request/<int:product_id>", methods=["POST"])
@login_required
def make_request(product_id):
    """สั่งจองพรีออเดอร์ -> บันทึกคำขอ แล้วแจ้งว่าร้านจะติดต่อกลับ"""
    user = get_current_user()
    qty = request.form.get("quantity", type=int) or 1
    qty = max(1, qty)

    product = db.query(
        "SELECT id, name FROM products WHERE id = %s AND is_active = TRUE AND is_preorder = TRUE",
        (product_id,),
        fetchone=True,
    )
    if not product:
        flash("ไม่พบสินค้าพรีออเดอร์นี้", "danger")
        return redirect(url_for("preorder.index"))

    db.query(
        """INSERT INTO preorder_requests (user_id, product_id, product_name, quantity)
           VALUES (%s, %s, %s, %s)""",
        (user["id"], product_id, product["name"], qty),
        commit=True,
    )
    from app import settings
    flash(f"ส่งคำสั่งจองเรียบร้อย {settings.get('preorder_message')}", "success")
    return redirect(url_for("preorder.my_requests"))


@bp.route("/my-requests")
@login_required
def my_requests():
    """ประวัติการสั่งจองพรีออเดอร์ของลูกค้า"""
    user = get_current_user()
    rows = db.query(
        """SELECT id, product_name, quantity, status, created_at
           FROM preorder_requests WHERE user_id = %s ORDER BY created_at DESC""",
        (user["id"],),
        fetchall=True,
    )
    return render_template("preorder/my_requests.html", requests=rows)


@bp.route("/cancel/<int:request_id>", methods=["POST"])
@login_required
def cancel_request(request_id):
    """ยกเลิกพรีออเดอร์ได้เองถ้าสถานะยังเป็น 'รอติดต่อกลับ' (ร้านยังไม่ตอบ)"""
    user = get_current_user()
    pr = db.query(
        "SELECT id, status FROM preorder_requests WHERE id = %s AND user_id = %s",
        (request_id, user["id"]),
        fetchone=True,
    )
    if not pr:
        flash("ไม่พบรายการนี้", "danger")
    elif pr["status"] != "รอติดต่อกลับ":
        flash("ไม่สามารถยกเลิกได้ เนื่องจากทางร้านได้ดำเนินการแล้ว", "warning")
    else:
        db.query(
            "UPDATE preorder_requests SET status = 'ยกเลิกโดยลูกค้า' WHERE id = %s AND user_id = %s",
            (request_id, user["id"]),
            commit=True,
        )
        flash("ยกเลิกพรีออเดอร์แล้ว", "success")
    return redirect(url_for("preorder.my_requests"))
