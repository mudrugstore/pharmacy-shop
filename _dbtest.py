"""
ทดสอบ integration เต็มรูปแบบกับฐานข้อมูล PostgreSQL จริง
วิธีใช้: ตั้ง DATABASE_URL ไปยัง Postgres (Supabase หรือ local) แล้วรัน
    python _dbtest.py
สคริปต์นี้จะสร้างตาราง -> สมัคร user -> admin เพิ่มหมวดหมู่/สินค้า ->
user สั่งซื้อ (ตรวจตัดสต็อก) -> พรีออเดอร์ -> รีเซ็ตรหัส
"""
import os
os.environ.setdefault("SECRET_KEY", "test")

from app import create_app
from app import db

app = create_app()
client = app.test_client()
PHONE = "0891112222"


def reset_tables():
    db.query("DROP TABLE IF EXISTS order_items, orders, preorder_requests, products, categories CASCADE", commit=True)
    # ลบ user ทดสอบ (ไม่ลบ admin)
    db.query("DELETE FROM users WHERE phone = %s", (PHONE,), commit=True)
    db.init_schema()


def main():
    reset_tables()

    # 1) สมัครสมาชิก
    r = client.post("/register", data={"name": "ทดสอบ", "phone": PHONE, "password": "123456", "confirm": "123456"}, follow_redirects=True)
    assert r.status_code == 200
    u = db.query("SELECT id FROM users WHERE phone = %s", (PHONE,), fetchone=True)
    assert u, "สมัครไม่สำเร็จ"
    print("OK: สมัครสมาชิก")

    # 2) login user
    r = client.post("/login", data={"phone": PHONE, "password": "123456"}, follow_redirects=True)
    assert r.status_code == 200
    print("OK: login user")

    # เตรียมข้อมูลผ่าน SQL ตรง (จำลองฝั่ง admin)
    cat_id = db.query("INSERT INTO categories (name) VALUES ('ยาแก้ปวด') RETURNING id", fetchone=True)["id"]
    prod_id = db.query(
        "INSERT INTO products (category_id, name, price, stock) VALUES (%s, 'พารา', 25.00, 10) RETURNING id",
        (cat_id,), fetchone=True,
    )["id"]
    pre_id = db.query(
        "INSERT INTO products (name, price, stock, is_preorder) VALUES ('วัคซีน', 500, 0, TRUE) RETURNING id",
        fetchone=True,
    )["id"]
    print("OK: เตรียมหมวดหมู่/สินค้า")

    # 3) เพิ่มลงตะกร้า + สั่งซื้อ 3 ชิ้น
    client.post(f"/cart/add/{prod_id}", data={"quantity": 3}, follow_redirects=True)
    client.post("/checkout", data={"note": "ทดสอบ"}, follow_redirects=True)
    stock = db.query("SELECT stock FROM products WHERE id = %s", (prod_id,), fetchone=True)["stock"]
    assert stock == 7, f"ตัดสต็อกผิด เหลือ {stock} (ควรเป็น 7)"
    order = db.query("SELECT total FROM orders WHERE user_id = %s", (u["id"],), fetchone=True)
    assert float(order["total"]) == 75.0, f"ยอดรวมผิด {order['total']}"
    print("OK: สั่งซื้อ + ตัดสต็อกถูกต้อง (10 -> 7, ยอด 75.00)")

    # 4) พรีออเดอร์
    client.post(f"/preorder/request/{pre_id}", data={"quantity": 2}, follow_redirects=True)
    pr = db.query("SELECT quantity, status FROM preorder_requests WHERE product_id = %s", (pre_id,), fetchone=True)
    assert pr and pr["quantity"] == 2 and pr["status"] == "รอติดต่อกลับ"
    print("OK: พรีออเดอร์")

    # 5) รีเซ็ตรหัส -> ต้องตั้งใหม่
    db.query("UPDATE users SET must_reset_password = TRUE WHERE id = %s", (u["id"],), commit=True)
    r = client.get("/orders", follow_redirects=False)
    assert r.status_code in (302, 308), "ควร redirect ไปตั้งรหัสใหม่"
    r = client.post("/force-reset", data={"password": "newpass", "confirm": "newpass"}, follow_redirects=True)
    flag = db.query("SELECT must_reset_password FROM users WHERE id = %s", (u["id"],), fetchone=True)["must_reset_password"]
    assert flag is False, "ตั้งรหัสใหม่แล้ว flag ควรเป็น false"
    print("OK: flow รีเซ็ต+ตั้งรหัสใหม่")

    print("\nDBTEST PASSED - ทุก flow ทำงานถูกต้อง")


if __name__ == "__main__":
    main()
