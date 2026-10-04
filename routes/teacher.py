from datetime import timedelta
from collections import Counter

from flask import Blueprint, Response, abort, current_app, flash, g, redirect, render_template, request, url_for
from sqlalchemy.exc import SQLAlchemyError

from extensions import db
from models import AttendanceTask, Student
from routes.auth import role_required
from services.attendance import freeze_roster, task_roster
from services.exports import csv_content
from services.navigation import task_context
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
    return render_template("teacher/dashboard.html", items=items, counts=Counter(state for _, state, _ in items), updated_at=now)


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
            flash("任务已发布，班级名单已固定。可在此查看签到进度、调整记录或导出名单。", "success")
            return redirect(url_for("teacher.results", task_id=task.id))
        except ValueError as exc:
            error = str(exc)
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("创建签到任务失败")
            return render_template("teacher/create.html", classes=classes, values=values,
                                   error="任务未创建成功，已保留填写内容，请稍后重试。"), 500
    return render_template("teacher/create.html", classes=classes, values=values, error=error), (400 if error else 200)


@bp.get("/tasks/<int:task_id>")
@role_required("teacher")
def results(task_id):
    task = db.get_or_404(AttendanceTask, task_id)
    if task.teacher_id != g.user.id:
        abort(403)
    rows, stats = task_roster(task)
    return render_template("teacher/results.html", task=task, rows=rows, stats=stats, context=task_context(request.args),
                           state=task_state(task, current_app.config["NOW"]()))


@bp.get("/tasks/<int:task_id>/export.csv")
@role_required("teacher")
def export_results(task_id):
    task = db.get_or_404(AttendanceTask, task_id)
    if task.teacher_id != g.user.id:
        abort(403)
    rows, _ = task_roster(task)
    state = task_state(task, current_app.config["NOW"]())
    missing = "缺勤" if state == "已结束" else "未开始" if state == "未开始" else "未签到"
    data = [["任务名称", "任务班级", "学号", "姓名", "当前班级", "签到状态", "签到来源", "记录时间（北京时间）", "距中心（米）"]]
    for student, record in rows:
        data.append([task.title, task.target_class_name, student.student_no, student.name, student.class_name,
                     "已签到" if record else missing,
                     ("定位签到" if record.has_location else "教师补签") if record else "",
                     beijing_time(record.checkin_time) if record else "",
                     f"{record.distance_meters:.2f}" if record and record.has_location else ""])
    return Response(csv_content(data), content_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="attendance-{task.id}.csv"'})
