"""ใส่ข้อมูลตัวอย่างสำหรับดูเว็บในเครื่อง (หมวดหมู่ + สินค้า + สินค้าพรีออเดอร์)"""
import os
os.environ.setdefault("SECRET_KEY", "local-dev")

from app import create_app
from app import db

app = create_app()

with app.app_context():
    # ล้างข้อมูลสินค้า/หมวดหมู่เดิมก่อน (ไม่แตะ users)
    db.query("DELETE FROM order_items", commit=True)
    db.query("DELETE FROM orders", commit=True)
    db.query("DELETE FROM preorder_requests", commit=True)
    db.query("DELETE FROM products", commit=True)
    db.query("DELETE FROM categories", commit=True)

    cats = {}
    for name in ["ยาแก้ปวด/ลดไข้", "ยาแก้แพ้", "วิตามิน/อาหารเสริม", "เวชภัณฑ์"]:
        row = db.query("INSERT INTO categories (name) VALUES (%s) RETURNING id", (name,), fetchone=True)
        cats[name] = row["id"]

    products = [
        ("ยาแก้ปวด/ลดไข้", "พาราเซตามอล 500mg (10 เม็ด)", "บรรเทาอาการปวด ลดไข้", 15.00, 120),
        ("ยาแก้ปวด/ลดไข้", "ไอบูโพรเฟน 400mg (10 เม็ด)", "ลดการอักเสบ บรรเทาปวด", 35.00, 80),
        ("ยาแก้แพ้", "เซทิริซีน 10mg (10 เม็ด)", "บรรเทาอาการแพ้ คัดจมูก", 45.00, 60),
        ("ยาแก้แพ้", "คลอร์เฟนิรามีน (10 เม็ด)", "ยาแก้แพ้ ลดน้ำมูก", 12.00, 100),
        ("วิตามิน/อาหารเสริม", "วิตามินซี 1000mg (30 เม็ด)", "เสริมภูมิคุ้มกัน", 180.00, 40),
        ("วิตามิน/อาหารเสริม", "น้ำมันปลา Fish Oil (60 แคปซูล)", "บำรุงสมองและหัวใจ", 320.00, 25),
        ("เวชภัณฑ์", "หน้ากากอนามัย (กล่อง 50 ชิ้น)", "ป้องกันฝุ่นและเชื้อโรค", 65.00, 200),
        ("เวชภัณฑ์", "แอลกอฮอล์เจล 500ml", "ทำความสะอาดมือ", 55.00, 0),  # หมดสต็อก
    ]
    for cat, name, desc, price, stock in products:
        db.query(
            """INSERT INTO products (category_id, name, description, price, stock, is_preorder)
               VALUES (%s, %s, %s, %s, %s, FALSE)""",
            (cats[cat], name, desc, price, stock), commit=True,
        )

    # สินค้าพรีออเดอร์
    preorders = [
        ("วัคซีนไข้หวัดใหญ่ (จองล่วงหน้า)", "เปิดจองล็อตใหม่ ร้านจะติดต่อนัดวันฉีด", 850.00),
        ("เครื่องวัดความดันดิจิทัล (สั่งจอง)", "รุ่นใหม่ สินค้ากำลังเข้า", 1290.00),
    ]
    for name, desc, price in preorders:
        db.query(
            """INSERT INTO products (name, description, price, stock, is_preorder)
               VALUES (%s, %s, %s, 0, TRUE)""",
            (name, desc, price), commit=True,
        )

    print("SEED DONE: ใส่ข้อมูลตัวอย่างเรียบร้อย")
