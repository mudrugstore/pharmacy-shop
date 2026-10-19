"""
สร้างรายงาน Excel (.xlsx) สำหรับหน้าแอดมิน
- รายงานทุกชนิดดึงข้อมูล "ทั้งหมด" (ไม่จำกัด 100 แถวเหมือนหน้าแสดงผล) เพื่อให้รายงานครบถ้วน
- จัดรูปแบบละเอียด: หัวตารางสีธีม, ตรึงหัวตาราง, ปรับความกว้างคอลัมน์อัตโนมัติ,
  แถวสรุปท้ายตาราง, เวลาเป็นเวลาประเทศไทย
"""
from io import BytesIO
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from app import db

THAI_TZ = timezone(timedelta(hours=7))

# ---------- สไตล์กลาง ----------
_HEADER_FILL = PatternFill("solid", fgColor="EE4D2D")   # ส้ม Shopee
_HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
_TITLE_FONT = Font(bold=True, size=14, color="EE4D2D")
_SUB_FONT = Font(italic=True, size=9, color="808080")
_SUMMARY_FONT = Font(bold=True, size=11)
_SUMMARY_FILL = PatternFill("solid", fgColor="FBE9E5")
_CENTER = Alignment(horizontal="center", vertical="center")
_LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)
_RIGHT = Alignment(horizontal="right", vertical="center")
_thin = Side(style="thin", color="DDDDDD")
_BORDER = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)


def _fmt_dt(value, fmt="%d/%m/%Y %H:%M"):
    """datetime (UTC) -> ข้อความเวลาประเทศไทย"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(THAI_TZ).strftime(fmt)


def _build_sheet(ws, title, columns, rows, summary=None):
    """
    สร้างเนื้อหาในชีต
    - columns: list ของ (header, key, width, align)  align: 'l'/'c'/'r'
    - rows: list ของ dict
    - summary: list ของ (label_col_index, value) แถวสรุปท้าย (optional)
    """
    ncol = len(columns)
    # แถวที่ 1: ชื่อรายงาน (merge)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncol)
    c = ws.cell(row=1, column=1, value=title)
    c.font = _TITLE_FONT
    c.alignment = Alignment(horizontal="left", vertical="center")
    # แถวที่ 2: วันเวลาที่ออกรายงาน
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ncol)
    gen = ws.cell(row=2, column=1,
                  value="ออกรายงานเมื่อ %s (เวลาประเทศไทย) · รวม %d รายการ"
                        % (datetime.now(THAI_TZ).strftime("%d/%m/%Y %H:%M"), len(rows)))
    gen.font = _SUB_FONT

    header_row = 4
    # หัวตาราง
    align_map = {"l": _LEFT, "c": _CENTER, "r": _RIGHT}
    for j, (header, _key, width, _align) in enumerate(columns, start=1):
        cell = ws.cell(row=header_row, column=j, value=header)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = _CENTER
        cell.border = _BORDER
        ws.column_dimensions[get_column_letter(j)].width = width

    # ข้อมูล
    r = header_row + 1
    for row in rows:
        for j, (_header, key, _width, align) in enumerate(columns, start=1):
            val = row.get(key)
            if isinstance(val, Decimal):
                val = float(val)
            cell = ws.cell(row=r, column=j, value=val)
            cell.alignment = align_map.get(align, _LEFT)
            cell.border = _BORDER
        r += 1

    # แถวสรุป
    if summary:
        for col_idx, value in summary:
            cell = ws.cell(row=r, column=col_idx, value=value)
            cell.font = _SUMMARY_FONT
            cell.fill = _SUMMARY_FILL
            cell.alignment = _RIGHT if col_idx > 1 else _LEFT

    # ตรึงหัวตาราง (ให้เลื่อนดูข้อมูลได้โดยหัวค้าง)
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)


def _save(wb):
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def _timestamp():
    return datetime.now(THAI_TZ).strftime("%Y%m%d_%H%M")


# ======================================================================
# รายงานแต่ละชนิด: คืน (bytes, filename)
# ======================================================================

def products_report():
    rows = db.query(
        """SELECT p.id, p.name, c.name AS category, p.price, p.stock,
                  p.is_preorder, p.is_active, p.badge_text, p.created_at
           FROM products p LEFT JOIN categories c ON p.category_id = c.id
           ORDER BY p.created_at DESC""",
        fetchall=True,
    )
    data = []
    total_stock_value = Decimal("0")
    for x in rows:
        total_stock_value += (x["price"] or 0) * (x["stock"] or 0)
        data.append({
            "id": x["id"],
            "name": x["name"],
            "category": x["category"] or "ไม่ระบุ",
            "price": float(x["price"] or 0),
            "stock": x["stock"],
            "type": "พรีออเดอร์" if x["is_preorder"] else "ขายปกติ",
            "active": "แสดง" if x["is_active"] else "ซ่อน",
            "badge": x["badge_text"] or "",
            "created": _fmt_dt(x["created_at"]),
        })
    columns = [
        ("รหัส", "id", 8, "c"),
        ("ชื่อสินค้า", "name", 34, "l"),
        ("หมวดหมู่", "category", 18, "l"),
        ("ราคา (บาท)", "price", 14, "r"),
        ("สต็อก", "stock", 10, "r"),
        ("ประเภท", "type", 12, "c"),
        ("สถานะ", "active", 10, "c"),
        ("ป้าย", "badge", 12, "l"),
        ("วันที่เพิ่ม", "created", 18, "c"),
    ]
    wb = Workbook(); ws = wb.active; ws.title = "สินค้า"
    _build_sheet(ws, "รายงานสินค้า", columns, data,
                 summary=[(2, "มูลค่าสต็อกรวม (ราคา x จำนวน)"), (4, float(total_stock_value))])
    return _save(wb), "products_%s.xlsx" % _timestamp()


def categories_report():
    rows = db.query(
        """SELECT c.id, c.name, COUNT(p.id) AS product_count, c.created_at
           FROM categories c LEFT JOIN products p ON p.category_id = c.id
           GROUP BY c.id, c.name, c.created_at ORDER BY c.name""",
        fetchall=True,
    )
    data = [{
        "id": x["id"], "name": x["name"],
        "count": x["product_count"], "created": _fmt_dt(x["created_at"]),
    } for x in rows]
    columns = [
        ("รหัส", "id", 8, "c"),
        ("ชื่อหมวดหมู่", "name", 34, "l"),
        ("จำนวนสินค้า", "count", 16, "r"),
        ("วันที่สร้าง", "created", 18, "c"),
    ]
    total = sum(x["count"] for x in data)
    wb = Workbook(); ws = wb.active; ws.title = "หมวดหมู่"
    _build_sheet(ws, "รายงานหมวดหมู่สินค้า", columns, data,
                 summary=[(2, "รวมสินค้าทั้งหมด"), (3, total)])
    return _save(wb), "categories_%s.xlsx" % _timestamp()


def orders_report():
    """รายงานคำสั่งซื้อ 2 ชีต: สรุปออเดอร์ + รายการสินค้าในแต่ละออเดอร์"""
    orders = db.query(
        """SELECT o.id, o.total, o.status, o.note, o.created_at,
                  u.name AS customer_name, u.phone
           FROM orders o JOIN users u ON o.user_id = u.id
           ORDER BY o.created_at DESC""",
        fetchall=True,
    )
    order_data = []
    grand_total = Decimal("0")
    for o in orders:
        if o["status"] != "ยกเลิกโดยลูกค้า":
            grand_total += (o["total"] or 0)
        order_data.append({
            "id": o["id"],
            "customer": o["customer_name"],
            "phone": o["phone"],
            "total": float(o["total"] or 0),
            "status": o["status"],
            "note": o["note"] or "",
            "created": _fmt_dt(o["created_at"]),
        })
    columns = [
        ("เลขที่", "id", 10, "c"),
        ("ลูกค้า", "customer", 22, "l"),
        ("เบอร์โทร", "phone", 16, "l"),
        ("ยอดรวม (บาท)", "total", 16, "r"),
        ("สถานะ", "status", 18, "c"),
        ("หมายเหตุ", "note", 30, "l"),
        ("วันที่สั่ง", "created", 18, "c"),
    ]
    wb = Workbook(); ws = wb.active; ws.title = "คำสั่งซื้อ"
    _build_sheet(ws, "รายงานคำสั่งซื้อ", columns, order_data,
                 summary=[(3, "ยอดขายรวม (ไม่รวมที่ยกเลิก)"), (4, float(grand_total))])

    # ชีตที่ 2: รายการสินค้าในแต่ละออเดอร์
    items = db.query(
        """SELECT oi.order_id, oi.product_name, oi.unit_price, oi.quantity,
                  (oi.unit_price * oi.quantity) AS subtotal
           FROM order_items oi
           ORDER BY oi.order_id DESC, oi.id""",
        fetchall=True,
    )
    item_data = [{
        "order_id": it["order_id"],
        "product": it["product_name"],
        "price": float(it["unit_price"] or 0),
        "qty": it["quantity"],
        "subtotal": float(it["subtotal"] or 0),
    } for it in items]
    icolumns = [
        ("เลขที่ออเดอร์", "order_id", 14, "c"),
        ("สินค้า", "product", 36, "l"),
        ("ราคา/ชิ้น", "price", 14, "r"),
        ("จำนวน", "qty", 10, "r"),
        ("รวม (บาท)", "subtotal", 16, "r"),
    ]
    ws2 = wb.create_sheet("รายการสินค้า")
    _build_sheet(ws2, "รายละเอียดสินค้าในคำสั่งซื้อ", icolumns, item_data)
    return _save(wb), "orders_%s.xlsx" % _timestamp()


def preorders_report():
    rows = db.query(
        """SELECT pr.id, pr.product_name, pr.quantity, pr.note, pr.status, pr.created_at,
                  u.name AS customer_name, u.phone
           FROM preorder_requests pr JOIN users u ON pr.user_id = u.id
           ORDER BY pr.created_at DESC""",
        fetchall=True,
    )
    data = [{
        "id": x["id"],
        "customer": x["customer_name"],
        "phone": x["phone"],
        "product": x["product_name"],
        "qty": x["quantity"],
        "note": x["note"] or "",
        "status": x["status"],
        "created": _fmt_dt(x["created_at"]),
    } for x in rows]
    columns = [
        ("เลขที่", "id", 10, "c"),
        ("ลูกค้า", "customer", 22, "l"),
        ("เบอร์โทร", "phone", 16, "l"),
        ("สินค้าที่จอง", "product", 28, "l"),
        ("จำนวน", "qty", 10, "r"),
        ("รายละเอียดจากลูกค้า", "note", 36, "l"),
        ("สถานะ", "status", 16, "c"),
        ("วันที่จอง", "created", 18, "c"),
    ]
    wb = Workbook(); ws = wb.active; ws.title = "พรีออเดอร์"
    _build_sheet(ws, "รายงานพรีออเดอร์", columns, data,
                 summary=[(4, "รวมรายการ"), (5, sum(x["qty"] for x in data))])
    return _save(wb), "preorders_%s.xlsx" % _timestamp()


def users_report():
    rows = db.query(
        """SELECT u.id, u.name, u.phone, u.must_reset_password, u.created_at,
                  (SELECT COUNT(*) FROM orders o WHERE o.user_id = u.id) AS order_count,
                  (SELECT COUNT(*) FROM preorder_requests pr WHERE pr.user_id = u.id) AS preorder_count
           FROM users u WHERE u.is_admin = FALSE ORDER BY u.created_at DESC""",
        fetchall=True,
    )
    data = [{
        "id": x["id"],
        "name": x["name"],
        "phone": x["phone"],
        "orders": x["order_count"],
        "preorders": x["preorder_count"],
        "locked": "รอตั้งรหัสใหม่" if x["must_reset_password"] else "ปกติ",
        "created": _fmt_dt(x["created_at"]),
    } for x in rows]
    columns = [
        ("รหัส", "id", 8, "c"),
        ("ชื่อ", "name", 24, "l"),
        ("เบอร์โทร", "phone", 16, "l"),
        ("จำนวนออเดอร์", "orders", 14, "r"),
        ("จำนวนพรีออเดอร์", "preorders", 16, "r"),
        ("สถานะบัญชี", "locked", 16, "c"),
        ("วันที่สมัคร", "created", 18, "c"),
    ]
    wb = Workbook(); ws = wb.active; ws.title = "ผู้ใช้"
    _build_sheet(ws, "รายงานผู้ใช้", columns, data,
                 summary=[(2, "จำนวนผู้ใช้ทั้งหมด"), (3, len(data))])
    return _save(wb), "users_%s.xlsx" % _timestamp()


# ทะเบียนรายงาน: key -> ฟังก์ชัน
REPORTS = {
    "products": products_report,
    "categories": categories_report,
    "orders": orders_report,
    "preorders": preorders_report,
    "users": users_report,
}
