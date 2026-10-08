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


def _request_conn():
    """
    คืน connection ที่ใช้ร่วมกันตลอด 1 request (เก็บใน Flask g) เพื่อ performance:
    แทนที่จะเปิด connection ใหม่ทุก query (ช้าเพราะ TCP+TLS handshake กับ Supabase)
    เราเปิดครั้งเดียวต่อ request แล้ว reuse จนจบ request จึงปิด (teardown)
    ถ้าอยู่นอก request context (เช่นตอน startup) จะคืน None ให้เปิด connection ชั่วคราวแทน
    """
    try:
        from flask import g, has_request_context
    except Exception:
        return None
    if not has_request_context():
        return None
    conn = getattr(g, "_db_conn", None)
    if conn is None or conn.closed:
        conn = _connect()
        g._db_conn = conn
    return conn


def close_request_conn(exc=None):
    """ปิด connection ของ request ตอนจบ (เรียกจาก teardown_appcontext)"""
    from flask import g
    conn = getattr(g, "_db_conn", None)
    if conn is not None:
        try:
            if exc is None:
                conn.commit()
            else:
                conn.rollback()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        g._db_conn = None


@contextmanager
def get_conn():
    """
    คืน connection สำหรับใช้งาน (reuse ต่อ request ถ้าอยู่ใน request context
    มิฉะนั้นเปิดชั่วคราว) ใช้สำหรับงานที่ต้องคุม transaction เอง เช่น checkout
    """
    if _database_url is None:
        raise RuntimeError("ยังไม่ได้ตั้งค่า DATABASE_URL เรียก init_pool() ก่อน")
    shared = _request_conn()
    if shared is not None:
        yield shared   # ไม่ปิดที่นี่ ปล่อยให้ teardown ปิดตอนจบ request
    else:
        conn = _connect()
        try:
            yield conn
        finally:
            conn.close()


def query(sql, params=None, fetchone=False, fetchall=False, commit=False):
    """
    ฟังก์ชันกลางสำหรับรันคำสั่ง SQL
    - fetchone: คืนแถวเดียว (dict) หรือ None
    - fetchall: คืนทุกแถว (list ของ dict)
    reuse connection เดียวต่อ request (เร็วขึ้น) และ retry ถ้า connection ถูกตัด
    """
    import time

    attempts = 3
    for i in range(attempts):
        shared = _request_conn()
        conn = shared if shared is not None else _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
                result = None
                if fetchone:
                    result = cur.fetchone()
                elif fetchall:
                    result = cur.fetchall()
            if shared is None:
                conn.commit()
            return result
        except (psycopg.OperationalError, psycopg.InterfaceError):
            # connection เสีย: ปิดทิ้งแล้วลองใหม่ด้วย connection ใหม่
            try:
                conn.rollback()
            except Exception:
                pass
            if shared is not None:
                try:
                    conn.close()
                except Exception:
                    pass
                from flask import g
                g._db_conn = None
            else:
                try:
                    conn.close()
                except Exception:
                    pass
            if i == attempts - 1:
                raise
            time.sleep(0.5 * (i + 1))
        finally:
            if shared is None and not conn.closed:
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
        badge_text  TEXT DEFAULT '',
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
    -- index ช่วย query หน้าร้าน: กรอง active + ไม่ใช่พรีออเดอร์ แล้วเรียงตามชื่อ
    CREATE INDEX IF NOT EXISTS idx_products_listing ON products(is_active, is_preorder, name);
    CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
    CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
    CREATE INDEX IF NOT EXISTS idx_preorder_user ON preorder_requests(user_id);
    CREATE INDEX IF NOT EXISTS idx_banners_order ON banners(is_active, sort_order);

    -- migration: เพิ่มคอลัมน์ให้ตารางเดิมที่สร้างไว้ก่อนหน้า (ปลอดภัย รันซ้ำได้)
    ALTER TABLE categories ADD COLUMN IF NOT EXISTS image_url TEXT DEFAULT '';
    ALTER TABLE banners ADD COLUMN IF NOT EXISTS display_page TEXT NOT NULL DEFAULT 'both';
    ALTER TABLE products ADD COLUMN IF NOT EXISTS badge_text TEXT DEFAULT '';
    -- ติดตามว่าลูกค้าเห็นการอัปเดตสถานะล่าสุดหรือยัง (สำหรับ badge แจ้งเตือน)
    ALTER TABLE orders ADD COLUMN IF NOT EXISTS seen_by_user BOOLEAN NOT NULL DEFAULT TRUE;
    ALTER TABLE preorder_requests ADD COLUMN IF NOT EXISTS seen_by_user BOOLEAN NOT NULL DEFAULT TRUE;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        conn.commit()
