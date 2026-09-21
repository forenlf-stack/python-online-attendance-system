from functools import wraps

from flask import Blueprint, abort, g, jsonify, redirect, render_template, request, session, url_for

from extensions import db
from models import Student, Teacher

bp = Blueprint("auth", __name__)


def role_required(role):
    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("user_id") or session.get("role") not in ("teacher", "student"):
                if request.is_json:
                    return jsonify(success=False, message="请先登录"), 401
                return redirect(url_for("auth.login"))
            if session["role"] != role:
                abort(403)
            model = Teacher if role == "teacher" else Student
            g.user = db.session.get(model, session["user_id"])
            if g.user is None:
                session.clear()
                if request.is_json:
                    return jsonify(success=False, message="登录已失效，请重新登录"), 401
                return redirect(url_for("auth.login"))
            return view(*args, **kwargs)
        return wrapped
    return decorate


@bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        role = request.form.get("role")
        account = request.form.get("account", "").strip()
        password = request.form.get("password", "")
        user = None
        if role == "teacher":
            user = db.session.scalar(db.select(Teacher).where(Teacher.teacher_no == account))
        elif role == "student":
            user = db.session.scalar(db.select(Student).where(Student.student_no == account))
        if user is not None and user.check_password(password):
            session.clear()
            session.update(role=role, user_id=user.id)
            return redirect(url_for(f"{role}.dashboard"))
        error = "身份、账号或密码错误"
    return render_template("login.html", error=error), (401 if error else 200)


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
