"""ระบบสมัครสมาชิก / เข้าสู่ระบบ / ออกจากระบบ / ตั้งรหัสใหม่"""
import re
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, session, g,
)
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.auth_utils import get_current_user

bp = Blueprint("auth", __name__)

PHONE_RE = re.compile(r"^0\d{8,9}$")  # เบอร์ไทย 9-10 หลัก ขึ้นต้นด้วย 0


def _clean_phone(phone):
    return re.sub(r"[\s-]", "", phone or "")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if get_current_user():
        return redirect(url_for("shop.index"))

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        phone = _clean_phone(request.form.get("phone"))
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""

        errors = []
        if not name:
            errors.append("กรุณากรอกชื่อ")
        if not PHONE_RE.match(phone):
            errors.append("เบอร์โทรไม่ถูกต้อง (ต้องขึ้นต้นด้วย 0 และมี 9-10 หลัก)")
        if len(password) < 6:
            errors.append("รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร")
        if password != confirm:
            errors.append("รหัสผ่านยืนยันไม่ตรงกัน")

        if not errors:
            exists = db.query("SELECT id FROM users WHERE phone = %s", (phone,), fetchone=True)
            if exists:
                errors.append("เบอร์โทรนี้ถูกใช้สมัครแล้ว")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("auth/register.html", name=name, phone=phone)

        db.query(
            "INSERT INTO users (name, phone, password_hash) VALUES (%s, %s, %s)",
            (name, phone, generate_password_hash(password)),
            commit=True,
        )
        flash("สมัครสมาชิกสำเร็จ กรุณาเข้าสู่ระบบ", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if get_current_user():
        return redirect(url_for("shop.index"))

    if request.method == "POST":
        phone = _clean_phone(request.form.get("phone"))
        password = request.form.get("password") or ""

        user = db.query(
            "SELECT id, password_hash, is_admin, must_reset_password FROM users WHERE phone = %s",
            (phone,),
            fetchone=True,
        )
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("เบอร์โทรหรือรหัสผ่านไม่ถูกต้อง", "danger")
            return render_template("auth/login.html", phone=phone)

        session.clear()
        session["user_id"] = user["id"]

        if user["must_reset_password"]:
            flash("บัญชีของคุณถูกรีเซ็ตรหัส กรุณาตั้งรหัสผ่านใหม่", "warning")
            return redirect(url_for("auth.force_reset"))

        flash("เข้าสู่ระบบสำเร็จ", "success")
        if user["is_admin"]:
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("shop.index"))

    return render_template("auth/login.html")


@bp.route("/logout")
def logout():
    session.clear()
    g.pop("user", None)
    flash("ออกจากระบบแล้ว", "info")
    return redirect(url_for("auth.login"))


@bp.route("/forgot-password")
def forgot():
    """หน้าแจ้งเตือนให้ติดต่อร้านเพื่อขอรีเซ็ตรหัส (ไม่มี OTP/อีเมล)"""
    return render_template("auth/forgot.html")


@bp.route("/force-reset", methods=["GET", "POST"])
def force_reset():
    """
    หน้าให้ user ตั้งรหัสใหม่หลังถูกแอดมินรีเซ็ต
    เข้าได้ต่อเมื่อ login แล้วและ must_reset_password = true
    """
    user_id = session.get("user_id")
    if not user_id:
        flash("กรุณาเข้าสู่ระบบก่อน", "warning")
        return redirect(url_for("auth.login"))

    user = db.query(
        "SELECT id, must_reset_password FROM users WHERE id = %s", (user_id,), fetchone=True
    )
    if not user or not user["must_reset_password"]:
        return redirect(url_for("shop.index"))

    if request.method == "POST":
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""
        if len(password) < 6:
            flash("รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร", "danger")
        elif password != confirm:
            flash("รหัสผ่านยืนยันไม่ตรงกัน", "danger")
        else:
            db.query(
                "UPDATE users SET password_hash = %s, must_reset_password = FALSE WHERE id = %s",
                (generate_password_hash(password), user_id),
                commit=True,
            )
            flash("ตั้งรหัสผ่านใหม่สำเร็จ", "success")
            return redirect(url_for("shop.index"))

    return render_template("auth/force_reset.html")
