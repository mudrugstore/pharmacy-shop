"""
จัดการการเชื่อมต่อฐานข้อมูล PostgreSQL (Supabase) ด้วย psycopg v3

หมายเหตุสำคัญ: ใช้กับ Supabase Transaction Pooler (port 6543) ซึ่งทำหน้าที่ pool
connection ให้ฝั่งเซิร์ฟเวอร์อยู่แล้ว เราจึง "ไม่ pool ซ้ำ" ที่ฝั่ง client แต่เปิด
connection ใหม่ต่อ request แล้วปิดทันที (เหมาะกับ transaction pooler ที่สุด)
และปิด prepared statements (prepare_threshold=None) เพราะ transaction pooler
ไม่รองรับ prepared statements
"""
from contextlib import contextmanager
import psycopg
from psycopg.rows import dict_row

_database_url = None


def init_pool(database_url):
    """เก็บ connection string ไว้ใช้ (ชื่อฟังก์ชันคงเดิมเพื่อความเข้ากันได้)"""
    global _database_url
    if not database_url:
        raise RuntimeError("DATABASE_URL ยังไม่ได้ตั้งค่า กรุณาตั้งใน .env")
    _database_url = database_url


def _connect():
    """เปิด connection ใหม่ไปยัง Supabase (ปิด prepared statements สำหรับ transaction pooler)"""
    return psycopg.connect(
        _database_url,
        row_factory=dict_row,
        prepare_threshold=None,   # ต้องปิด: transaction pooler ไม่รองรับ prepared statements
        connect_timeout=15,
        autocommit=False,
    )


@contextmanager
def get_conn():
    """เปิด connection ต่อการใช้งาน แล้วปิดอัตโนมัติเมื่อเสร็จ"""
    if _database_url is None:
        raise RuntimeError("ยังไม่ได้ตั้งค่า DATABASE_URL เรียก init_pool() ก่อน")
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()


def query(sql, params=None, fetchone=False, fetchall=False, commit=False):
    """
    ฟังก์ชันกลางสำหรับรันคำสั่ง SQL (เปิด connection ใหม่ต่อ query)
    - fetchone: คืนแถวเดียว (dict) หรือ None
    - fetchall: คืนทุกแถว (list ของ dict)
    มี retry ถ้าเจอ connection error (เช่น pooler ตัด connection ชั่วคราว)
    """
    import time

    attempts = 3
    for i in range(attempts):
        conn = None
        try:
            conn = _connect()
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
                result = None
                if fetchone:
                    result = cur.fetchone()
                elif fetchall:
                    result = cur.fetchall()
            conn.commit()
            return result
        except (psycopg.OperationalError, psycopg.InterfaceError):
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            if i == attempts - 1:
                raise
            time.sleep(0.5 * (i + 1))
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass


def init_schema():
    """สร้างตารางทั้งหมดถ้ายังไม่มี (idempotent)"""
    schema_sql = """
    CREATE TABLE IF NOT EXISTS users (
        id              SERIAL PRIMARY KEY,
        name            TEXT NOT NULL,
        phone           TEXT UNIQUE NOT NULL,
        password_hash   TEXT NOT NULL,
        is_admin        BOOLEAN NOT NULL DEFAULT FALSE,
        must_reset_password BOOLEAN NOT NULL DEFAULT FALSE,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS categories (
        id          SERIAL PRIMARY KEY,
        name        TEXT NOT NULL,
        image_url   TEXT DEFAULT '',
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS products (
        id          SERIAL PRIMARY KEY,
        category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
        name        TEXT NOT NULL,
        description TEXT DEFAULT '',
        price       NUMERIC(10,2) NOT NULL DEFAULT 0,
        stock       INTEGER NOT NULL DEFAULT 0,
        image_url   TEXT DEFAULT '',
        is_preorder BOOLEAN NOT NULL DEFAULT FALSE,
        is_active   BOOLEAN NOT NULL DEFAULT TRUE,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS orders (
        id          SERIAL PRIMARY KEY,
        user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        total       NUMERIC(10,2) NOT NULL DEFAULT 0,
        status      TEXT NOT NULL DEFAULT 'รอดำเนินการ',
        note        TEXT DEFAULT '',
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS order_items (
        id              SERIAL PRIMARY KEY,
        order_id        INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
        product_id      INTEGER REFERENCES products(id) ON DELETE SET NULL,
        product_name    TEXT NOT NULL,
        unit_price      NUMERIC(10,2) NOT NULL DEFAULT 0,
        quantity        INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS preorder_requests (
        id              SERIAL PRIMARY KEY,
        user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        product_id      INTEGER REFERENCES products(id) ON DELETE SET NULL,
        product_name    TEXT NOT NULL,
        quantity        INTEGER NOT NULL DEFAULT 1,
        status          TEXT NOT NULL DEFAULT 'รอติดต่อกลับ',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS settings (
        key         TEXT PRIMARY KEY,
        value       TEXT NOT NULL DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS banners (
        id           SERIAL PRIMARY KEY,
        image_url    TEXT NOT NULL,
        link_url     TEXT DEFAULT '',
        sort_order   INTEGER NOT NULL DEFAULT 0,
        is_active    BOOLEAN NOT NULL DEFAULT TRUE,
        display_page TEXT NOT NULL DEFAULT 'both',
        created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id);
    CREATE INDEX IF NOT EXISTS idx_products_preorder ON products(is_preorder);
    CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
    CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
    CREATE INDEX IF NOT EXISTS idx_preorder_user ON preorder_requests(user_id);
    CREATE INDEX IF NOT EXISTS idx_banners_order ON banners(is_active, sort_order);

    -- migration: เพิ่มคอลัมน์ให้ตารางเดิมที่สร้างไว้ก่อนหน้า (ปลอดภัย รันซ้ำได้)
    ALTER TABLE categories ADD COLUMN IF NOT EXISTS image_url TEXT DEFAULT '';
    ALTER TABLE banners ADD COLUMN IF NOT EXISTS display_page TEXT NOT NULL DEFAULT 'both';
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        conn.commit()
