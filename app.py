import os
import secrets
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException

from extensions import csrf, db
from services.time_utils import beijing_time, utc_now


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        SQLALCHEMY_DATABASE_URI="sqlite:///attendance.db",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
        MAX_CONTENT_LENGTH=16 * 1024,
        NOW=utc_now,
    )
    if test_config:
        app.config.update(test_config)
    Path(app.instance_path).mkdir(exist_ok=True)
    db.init_app(app)
    csrf.init_app(app)
    from routes.auth import bp as auth_bp
    from routes.teacher import bp as teacher_bp
    from routes.student import bp as student_bp
    from routes.management import bp as management_bp
    app.register_blueprint(management_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(teacher_bp)
    app.register_blueprint(student_bp)
    app.jinja_env.filters["beijing"] = beijing_time

    @app.get("/")
    def index():
        role = session.get("role")
        return redirect(url_for(f"{role}.dashboard" if role in ("student", "teacher") else "auth.login"))

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        message = "安全校验失败，请刷新页面后重试（CSRF token 无效或已过期）。"
        if request.is_json:
            return jsonify(success=False, message=message), 400
        return render_template("error.html", message=message, code=400), 400

    @app.errorhandler(HTTPException)
    def http_error(error):
        message = {400: "请求参数有误", 403: "无权访问此内容", 404: "页面或任务不存在",
                   405: "不支持此请求方式", 413: "提交内容过大"}.get(error.code, "请求无法完成")
        if request.is_json:
            return jsonify(success=False, message=message), error.code
        return render_template("error.html", message=message, code=error.code), error.code

    @app.after_request
    def response_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        # OSM tiles require a Referer; cross-origin requests disclose only the origin.
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store"
        return response

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=False)
