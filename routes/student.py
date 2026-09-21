import sqlite3

from flask import Blueprint, abort, current_app, g, jsonify, render_template, request
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from extensions import db
from models import AttendanceAdjustment, AttendanceRecord, AttendanceTask, TaskMember
from routes.auth import role_required
from services.attendance import ACTION_LABELS, student_attendance
from services.geofence import calculate_distance, coordinates
from services.time_utils import task_state

bp = Blueprint("student", __name__, url_prefix="/student")


@bp.get("/")
@role_required("student")
def dashboard():
    now = current_app.config["NOW"]()
    items = []
    adjustments = {}
    for task, record, adjustment in student_attendance(g.user.id):
        state = "已签到" if record else ("已撤销" if adjustment and adjustment.action == "absent" else
            ("可以签到" if task_state(task, now) == "进行中" else task_state(task, now)))
        items.append((task, state))
        adjustments[task.id] = adjustment
    return render_template("student/dashboard.html", items=items, adjustments=adjustments)



@bp.get("/records")
@role_required("student")
def records():
    records = [record for _, record, _ in student_attendance(g.user.id) if record]
    records.sort(key=lambda record: record.checkin_time, reverse=True)
    history = db.session.scalars(db.select(AttendanceAdjustment).where(
        AttendanceAdjustment.student_id == g.user.id).order_by(AttendanceAdjustment.id.desc()).limit(50)).all()
    return render_template("student/records.html", records=records, history=history, actions=ACTION_LABELS)



def failure(message, code=400):
    return jsonify(success=False, message=message), code


@bp.post("/tasks/<int:task_id>/checkin")
@role_required("student")
def checkin(task_id):
    task = db.get_or_404(AttendanceTask, task_id)
    if db.session.get(TaskMember, (task.id, g.user.id)) is None:
        abort(403)
    now = current_app.config["NOW"]()
    if now < task.start_time:
        return failure("签到尚未开始")
    if now > task.end_time:
        return failure("签到已结束")
    adjustment = db.session.scalar(db.select(AttendanceAdjustment).where(
        AttendanceAdjustment.task_id == task_id, AttendanceAdjustment.student_id == g.user.id)
        .order_by(AttendanceAdjustment.version.desc()))
    if adjustment and adjustment.action != "restore":
        return failure("教师已调整此项签到，请查看个人记录；如需更正请联系教师。", 409)
    existing = db.select(AttendanceRecord).where(
        AttendanceRecord.task_id == task.id, AttendanceRecord.student_id == g.user.id)
    if db.session.scalar(existing):
        return failure("你已签到，请勿重复提交", 409)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return failure("请提交包含经纬度的 JSON 对象")
    try:
        lat, lon = coordinates(payload.get("latitude"), payload.get("longitude"))
    except ValueError as exc:
        return failure(str(exc))
    distance = calculate_distance(task.center_latitude, task.center_longitude, lat, lon)
    if distance > task.radius_meters:
        return failure(f"距离签到中心约 {distance:.2f} 米，允许半径 {task.radius_meters:g} 米，"
                       f"超出约 {distance - task.radius_meters:.2f} 米。")
    record = AttendanceRecord(task_id=task.id, student_id=g.user.id, checkin_time=now,
                              latitude=lat, longitude=lon, distance_meters=distance, status="success")
    db.session.add(record)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        # Only the specific SQLite composite uniqueness conflict is a duplicate check-in.
        if (getattr(exc.orig, "sqlite_errorcode", None) == sqlite3.SQLITE_CONSTRAINT_UNIQUE
                and "attendance_record.task_id, attendance_record.student_id" in str(exc.orig)):
            return failure("你已签到，请勿重复提交", 409)
        current_app.logger.exception("签到数据库约束错误")
        return failure("保存失败，请稍后重试", 500)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("签到数据库错误")
        return failure("保存失败，请稍后重试", 500)
    return jsonify(success=True, message=f"签到成功，距离签到中心约 {distance:.2f} 米。", distance_meters=distance)
