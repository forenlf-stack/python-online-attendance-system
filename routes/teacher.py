from datetime import timedelta

from flask import Blueprint, abort, current_app, g, redirect, render_template, request, url_for

from extensions import db
from models import AttendanceRecord, AttendanceTask, Student
from routes.auth import role_required
from services.attendance import freeze_roster, task_roster
from services.geofence import coordinates, finite_number
from services.time_utils import beijing_time, parse_beijing, task_state

bp = Blueprint("teacher", __name__, url_prefix="/teacher")


@bp.get("/")
@role_required("teacher")
def dashboard():
    tasks = db.session.scalars(db.select(AttendanceTask).where(
        AttendanceTask.teacher_id == g.user.id).order_by(AttendanceTask.created_at.desc())).all()
    now = current_app.config["NOW"]()
    items = [(task, task_state(task, now), task_roster(task)[1]) for task in tasks]
    return render_template("teacher/dashboard.html", items=items)


@bp.route("/tasks/new", methods=["GET", "POST"])
@role_required("teacher")
def create_task():
    classes = db.session.scalars(db.select(Student.class_name).distinct().order_by(Student.class_name)).all()
    now = current_app.config["NOW"]()
    values = dict(request.form) if request.method == "POST" else {
        "start_time": beijing_time(now, form=True),
        "end_time": beijing_time(now + timedelta(minutes=30), form=True), "radius_meters": "200"}
    error = None
    if request.method == "POST":
        try:
            title = values.get("title", "").strip()
            if not title or len(title) > 100:
                raise ValueError("签到名称须为 1–100 个字符")
            class_name = values.get("target_class_name", "")
            if class_name not in classes:
                raise ValueError("请选择现有学生班级")
            start = parse_beijing(values.get("start_time"))
            end = parse_beijing(values.get("end_time"))
            if start >= end:
                raise ValueError("开始时间必须早于结束时间")
            lat, lon = coordinates(values.get("center_latitude"), values.get("center_longitude"))
            radius = finite_number(values.get("radius_meters"), "半径")
            if radius <= 0:
                raise ValueError("半径必须大于 0 米")
            task = AttendanceTask(title=title, teacher_id=g.user.id, target_class_name=class_name,
                                  start_time=start, end_time=end, center_latitude=lat,
                                  center_longitude=lon, radius_meters=radius, created_at=now)
            db.session.add(task)
            db.session.flush()
            freeze_roster(task, now)
            db.session.commit()
            return redirect(url_for("teacher.results", task_id=task.id))
        except ValueError as exc:
            error = str(exc)
    return render_template("teacher/create.html", classes=classes, values=values, error=error), (400 if error else 200)


@bp.get("/tasks/<int:task_id>")
@role_required("teacher")
def results(task_id):
    task = db.get_or_404(AttendanceTask, task_id)
    if task.teacher_id != g.user.id:
        abort(403)
    rows, stats = task_roster(task)
    return render_template("teacher/results.html", task=task, rows=rows, stats=stats,
                           state=task_state(task, current_app.config["NOW"]()))
