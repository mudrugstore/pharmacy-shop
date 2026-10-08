"""ฝั่งลูกค้า: หน้าร้าน, ตะกร้า, สั่งซื้อ, ประวัติการสั่งซื้อ"""
from decimal import Decimal
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, session,
)
from app import db
from app.auth_utils import login_required, get_current_user

bp = Blueprint("shop", __name__)


def _get_cart():
    """ตะกร้าเก็บใน session เป็น dict {product_id(str): quantity(int)}"""
    return session.get("cart", {})


def _save_cart(cart):
    session["cart"] = cart
    session.modified = True


@bp.route("/")
def index():
    """หน้าร้าน: แสดงสินค้าทั่วไป กรองตามหมวดหมู่ และค้นหาด้วยคำค้น (q) ได้"""
    category_id = request.args.get("category", type=int)
    q = (request.args.get("q") or "").strip()
    categories = db.query("SELECT id, name, image_url FROM categories ORDER BY name", fetchall=True)

    # สร้างเงื่อนไขแบบ dynamic (ใส่ prefix p. ให้ชัดเจนตั้งแต่ต้น)
    where = ["p.is_active = TRUE", "p.is_preorder = FALSE"]
    params = []
    if category_id:
        where.append("p.category_id = %s")
        params.append(category_id)
    if q:
        where.append("(p.name ILIKE %s OR p.description ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%"])

    sql = (
        "SELECT p.id, p.name, p.description, p.price, p.stock, p.image_url, "
        "c.name AS category_name "
        "FROM products p LEFT JOIN categories c ON p.category_id = c.id "
        f"WHERE {' AND '.join(where)} ORDER BY p.name"
    )
    products = db.query(sql, tuple(params), fetchall=True)

    # ถ้าเป็น request แบบ AJAX (เปลี่ยนหมวดหมู่) คืนเฉพาะบล็อกรายการสินค้า ไม่โหลดทั้งหน้า
    if request.headers.get("X-Requested-With") == "fetch":
        return render_template(
            "shop/_product_grid.html",
            products=products,
            search_query=q,
        )

    # แบนเนอร์โฆษณา (แสดงเฉพาะหน้าแรก ไม่แสดงตอนค้นหา/กรองหมวด)
    # เลือกเฉพาะแบนเนอร์ที่ตั้งให้แสดงหน้าสินค้า ('shop') หรือทั้งสอง ('both')
    banners = []
    if not q and not category_id:
        banners = db.query(
            "SELECT image_url, link_url FROM banners "
            "WHERE is_active = TRUE AND display_page IN ('shop', 'both') "
            "ORDER BY sort_order, id",
            fetchall=True,
        )

    return render_template(
        "shop/index.html",
        products=products,
        categories=categories,
        selected_category=category_id,
        search_query=q,
        banners=banners,
    )


@bp.route("/product/<int:product_id>")
def product_detail(product_id):
    product = db.query(
        """SELECT p.id, p.name, p.description, p.price, p.stock, p.image_url,
                  p.is_preorder, c.name AS category_name
           FROM products p LEFT JOIN categories c ON p.category_id = c.id
           WHERE p.id = %s AND p.is_active = TRUE""",
        (product_id,),
        fetchone=True,
    )
    if not product:
        flash("ไม่พบสินค้านี้", "danger")
        return redirect(url_for("shop.index"))
    return render_template("shop/product_detail.html", product=product)


@bp.route("/cart")
@login_required
def cart():
    cart = _get_cart()
    items, total = _build_cart_items(cart)
    return render_template("shop/cart.html", items=items, total=total)


def _build_cart_items(cart):
    """รวมข้อมูลสินค้าในตะกร้าพร้อมคำนวณยอดรวม"""
    items = []
    total = Decimal("0")
    if not cart:
        return items, total
    ids = [int(pid) for pid in cart.keys()]
    rows = db.query(
        "SELECT id, name, price, stock, image_url FROM products WHERE id = ANY(%s)",
        (ids,),
        fetchall=True,
    )
    row_map = {r["id"]: r for r in rows}
    for pid_str, qty in cart.items():
        pid = int(pid_str)
        p = row_map.get(pid)
        if not p:
            continue
        subtotal = p["price"] * qty
        total += subtotal
        items.append({
            "id": pid,
            "name": p["name"],
            "price": p["price"],
            "stock": p["stock"],
            "image_url": p["image_url"],
            "quantity": qty,
            "subtotal": subtotal,
        })
    return items, total


@bp.route("/cart/add/<int:product_id>", methods=["POST"])
@login_required
def cart_add(product_id):
    qty = request.form.get("quantity", type=int) or 1
    product = db.query(
        "SELECT id, stock FROM products WHERE id = %s AND is_active = TRUE AND is_preorder = FALSE",
        (product_id,),
        fetchone=True,
    )
    if not product:
        flash("ไม่พบสินค้านี้", "danger")
        return redirect(url_for("shop.index"))
    if product["stock"] <= 0:
        flash("สินค้าหมดสต็อก", "warning")
        return redirect(url_for("shop.product_detail", product_id=product_id))

    cart = _get_cart()
    key = str(product_id)
    new_qty = cart.get(key, 0) + qty
    # ไม่ให้เกินสต็อก
    new_qty = min(new_qty, product["stock"])
    cart[key] = max(1, new_qty)
    _save_cart(cart)
    flash("เพิ่มลงตะกร้าแล้ว", "success")
    return redirect(url_for("shop.cart"))


@bp.route("/cart/update/<int:product_id>", methods=["POST"])
@login_required
def cart_update(product_id):
    qty = request.form.get("quantity", type=int) or 1
    cart = _get_cart()
    key = str(product_id)
    if key in cart:
        if qty <= 0:
            cart.pop(key)
        else:
            product = db.query("SELECT stock FROM products WHERE id = %s", (product_id,), fetchone=True)
            max_stock = product["stock"] if product else qty
            cart[key] = min(qty, max_stock)
        _save_cart(cart)
    return redirect(url_for("shop.cart"))


@bp.route("/cart/remove/<int:product_id>", methods=["POST"])
@login_required
def cart_remove(product_id):
    cart = _get_cart()
    cart.pop(str(product_id), None)
    _save_cart(cart)
    flash("ลบสินค้าออกจากตะกร้าแล้ว", "info")
    return redirect(url_for("shop.cart"))


@bp.route("/checkout", methods=["POST"])
@login_required
def checkout():
    """
    สร้างคำสั่งซื้อ ตัดสต็อกแบบ transaction (ล็อกแถวกันสต็อกชนกัน)
    ไม่มีระบบชำระเงิน -> แสดงข้อความให้ติดต่อร้าน
    """
    user = get_current_user()
    cart = _get_cart()
    if not cart:
        flash("ตะกร้าว่างเปล่า", "warning")
        return redirect(url_for("shop.index"))

    note = (request.form.get("note") or "").strip()

    order_id = None
    with db.get_conn() as conn:
        try:
            with conn.cursor() as cur:
                ids = [int(pid) for pid in cart.keys()]
                # ล็อกแถวสินค้าเพื่อกันการตัดสต็อกพร้อมกัน
                cur.execute(
                    "SELECT id, name, price, stock FROM products WHERE id = ANY(%s) FOR UPDATE",
                    (ids,),
                )
                rows = cur.fetchall()
                # cursor คืน dict (row_factory=dict_row)
                prod_map = {r["id"]: r for r in rows}

                # ตรวจสต็อกก่อน
                for pid_str, qty in cart.items():
                    pid = int(pid_str)
                    p = prod_map.get(pid)
                    if not p:
                        raise ValueError("มีสินค้าในตะกร้าที่ไม่พบแล้ว")
                    if p["stock"] < qty:
                        raise ValueError(f"สินค้า '{p['name']}' เหลือไม่พอ (คงเหลือ {p['stock']})")

                # คำนวณยอดรวม
                total = Decimal("0")
                for pid_str, qty in cart.items():
                    total += prod_map[int(pid_str)]["price"] * qty

                # สร้าง order
                cur.execute(
                    "INSERT INTO orders (user_id, total, note) VALUES (%s, %s, %s) RETURNING id",
                    (user["id"], total, note),
                )
                order_id = cur.fetchone()["id"]

                # สร้าง order_items + ตัดสต็อก
                for pid_str, qty in cart.items():
                    pid = int(pid_str)
                    p = prod_map[pid]
                    cur.execute(
                        """INSERT INTO order_items
                           (order_id, product_id, product_name, unit_price, quantity)
                           VALUES (%s, %s, %s, %s, %s)""",
                        (order_id, pid, p["name"], p["price"], qty),
                    )
                    cur.execute(
                        "UPDATE products SET stock = stock - %s WHERE id = %s",
                        (qty, pid),
                    )
                conn.commit()
        except Exception as e:
            conn.rollback()
            flash(f"สั่งซื้อไม่สำเร็จ: {e}", "danger")
            return redirect(url_for("shop.cart"))

    _save_cart({})
    from app import settings
    flash(f"สั่งซื้อสำเร็จ! {settings.get('checkout_message')}", "success")
    return redirect(url_for("shop.order_detail", order_id=order_id))


@bp.route("/orders")
@login_required
def orders():
    user = get_current_user()
    rows = db.query(
        "SELECT id, total, status, created_at FROM orders WHERE user_id = %s ORDER BY created_at DESC",
        (user["id"],),
        fetchall=True,
    )
    return render_template("shop/orders.html", orders=rows)


@bp.route("/orders/<int:order_id>")
@login_required
def order_detail(order_id):
    user = get_current_user()
    order = db.query(
        "SELECT id, total, status, note, created_at FROM orders WHERE id = %s AND user_id = %s",
        (order_id, user["id"]),
        fetchone=True,
    )
    if not order:
        flash("ไม่พบคำสั่งซื้อนี้", "danger")
        return redirect(url_for("shop.orders"))
    items = db.query(
        "SELECT product_name, unit_price, quantity FROM order_items WHERE order_id = %s",
        (order_id,),
        fetchall=True,
    )
    return render_template("shop/order_detail.html", order=order, items=items)


@bp.route("/help")
def help_page():
    """หน้าคู่มือการใช้งาน แสดงเนื้อหาตาม role ของผู้ใช้"""
    return render_template("shop/help.html")
