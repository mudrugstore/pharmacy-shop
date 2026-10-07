"""ตัวช่วยเกี่ยวกับการยืนยันตัวตนและสิทธิ์การเข้าถึง"""
from functools import wraps
from flask import session, redirect, url_for, flash, g
from app import db


def get_current_user():
    """ดึงข้อมูล user ปัจจุบันจาก session (cache ไว้ใน g ต่อ request)"""
    if "user" in g:
        return g.user
    user_id = session.get("user_id")
    if not user_id:
        g.user = None
        return None
    g.user = db.query(
        "SELECT id, name, phone, is_admin, must_reset_password FROM users WHERE id = %s",
        (user_id,),
        fetchone=True,
    )
    return g.user


def login_required(view):
    """ต้องล็อกอินก่อนถึงจะเข้าได้ และบังคับตั้งรหัสใหม่ถ้าถูกรีเซ็ต"""
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = get_current_user()
        if user is None:
            flash("กรุณาเข้าสู่ระบบก่อน", "warning")
            return redirect(url_for("auth.login"))
        if user["must_reset_password"]:
            flash("กรุณาตั้งรหัสผ่านใหม่ก่อนใช้งาน", "warning")
            return redirect(url_for("auth.force_reset"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    """ต้องเป็นแอดมินเท่านั้น"""
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = get_current_user()
        if user is None:
            flash("กรุณาเข้าสู่ระบบก่อน", "warning")
            return redirect(url_for("auth.login"))
        if not user["is_admin"]:
            flash("หน้านี้สำหรับผู้ดูแลระบบเท่านั้น", "danger")
            return redirect(url_for("shop.index"))
        return view(*args, **kwargs)
    return wrapped
