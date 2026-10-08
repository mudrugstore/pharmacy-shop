"""
Cache ในหน่วยความจำแบบง่าย สำหรับข้อมูลที่อ่านบ่อยแต่เปลี่ยนนานๆ ครั้ง
(settings, categories, banners) เพื่อลดจำนวน query/connection ไป Supabase

- มี TTL กันข้อมูลค้างนานเกินไป (เผื่อแก้จากหลาย instance/จาก Supabase ตรงๆ)
- invalidate() เรียกเมื่อ admin แก้ข้อมูล เพื่อให้ดึงใหม่ทันที

หมายเหตุ: cache อยู่ต่อ process (worker) เหมาะกับ Render free ที่รัน worker เดียว
ถ้ามีหลาย worker แต่ละตัวจะมี cache แยก แต่ TTL สั้นช่วยให้ sync กันในไม่กี่วินาที
"""
import time

_store = {}   # key -> (expire_ts, value)
_DEFAULT_TTL = 60  # วินาที


def get_or_set(key, loader, ttl=_DEFAULT_TTL):
    """คืนค่าจาก cache ถ้ายังไม่หมดอายุ มิฉะนั้นเรียก loader() แล้ว cache ไว้"""
    now = time.time()
    entry = _store.get(key)
    if entry is not None and entry[0] > now:
        return entry[1]
    value = loader()
    _store[key] = (now + ttl, value)
    return value


def invalidate(*keys):
    """ล้าง cache ของ key ที่ระบุ (เรียกเมื่อข้อมูลถูกแก้)"""
    if not keys:
        _store.clear()
        return
    for k in keys:
        _store.pop(k, None)
