"""จัดการการเชื่อมต่อฐานข้อมูล PostgreSQL (Supabase) ด้วย psycopg v3 + connection pool"""
from contextlib import contextmanager
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

_pool = None


def init_pool(database_url):
    """สร้าง connection pool ตอนแอปเริ่มทำงาน"""
    global _pool
    if _pool is None:
        if not database_url:
            raise RuntimeError("DATABASE_URL ยังไม่ได้ตั้งค่า กรุณาตั้งใน .env")
        # ตั้งค่าให้เหมาะกับ Supabase free tier (Transaction pooler port 6543):
        # - min_size=0: ไม่ถือ connection ค้างตอน idle (Supabase pooler ตัด idle connection
        #   เงียบๆ การถือค้างทำให้ pool แจก connection ตายแล้ว query พัง)
        # - max_size เล็ก: Supabase free จำกัด connection รวม ห้ามถือเยอะ
        # - max_lifetime สั้น: รีไซเคิล connection บ่อย กัน connection ตายจาก pooler
        # - max_idle สั้น: คืน connection ที่ว่างเร็ว
        # - timeout: รอ connection ไม่เกิน 10 วิ (ถ้าเกินค่อย error เร็วๆ ไม่ค้าง 30 วิ)
        # ไม่ใช้ check เพราะทำให้ pool พยายาม validate ทุก connection พร้อมกันตอน
        #   pooler ตัด connection → สร้างใหม่ไม่ทัน → PoolTimeout; ใช้ retry ใน query() แทน
        _pool = ConnectionPool(
            conninfo=database_url,
            min_size=0,
            max_size=4,
            max_idle=30,
            max_lifetime=600,
            timeout=10,
            reconnect_timeout=10,
            open=True,
            kwargs={"row_factory": dict_row},
        )
    return _pool


@contextmanager
def get_conn():
    """ยืม connection จาก pool แล้วคืนให้อัตโนมัติเมื่อใช้เสร็จ"""
    if _pool is None:
        raise RuntimeError("connection pool ยังไม่ถูกสร้าง เรียก init_pool() ก่อน")
    with _pool.connection() as conn:
        yield conn


def query(sql, params=None, fetchone=False, fetchall=False, commit=False):
    """
    ฟังก์ชันกลางสำหรับรันคำสั่ง SQL
    - fetchone: คืนแถวเดียว (dict) หรือ None
    - fetchall: คืนทุกแถว (list ของ dict)
    - commit: psycopg v3 จะ commit อัตโนมัติเมื่อออกจาก context (ไม่มี error)
      พารามิเตอร์ commit คงไว้เพื่อความชัดเจนของเจตนาเท่านั้น

    มี retry ถ้าเจอ connection error หรือ pool หยิบ connection ไม่ได้ (เช่น Supabase
    pooler ตัด connection ที่ค้างอยู่) โดยลองใหม่พร้อมหน่วงเล็กน้อยให้ pool สร้าง
    connection ใหม่ทัน
    """
    import time
    import psycopg
    from psycopg_pool import PoolTimeout

    attempts = 3
    for i in range(attempts):
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params or ())
                    if fetchone:
                        return cur.fetchone()
                    if fetchall:
                        return cur.fetchall()
                    return None
        except (psycopg.OperationalError, psycopg.InterfaceError, PoolTimeout):
            if i == attempts - 1:
                raise
            time.sleep(0.5 * (i + 1))  # หน่วงเพิ่มขึ้นก่อนลองใหม่ (0.5s, 1s)


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
