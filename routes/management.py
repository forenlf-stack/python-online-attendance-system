"""Teacher directory edits and auditable attendance corrections."""
from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from extensions import db
from models import AttendanceAdjustment, AttendanceRecord, AttendanceTask, Student, StudentChange, TaskMember
from routes.auth import role_required
from services.attendance import ACTION_LABELS, effective_record
from services.time_utils import task_state

bp = Blueprint("management", __name__, url_prefix="/teacher")


def clean_text(value, label, limit):
    value = value.strip()
    if not value or len(value) > limit or any(ord(char) < 32 for char in value):
        raise ValueError(f"{label}须为 1–{limit} 个字符，不能包含换行或控制字符")
    return value


def version_matches(raw, current):
    try:
        return int(raw) == current
    except (TypeError, ValueError):
        return False


@bp.get("/students")
@role_required("teacher")
def students():
    keyword = request.args.get("q", "").strip()[:80]
    selected_class = request.args.get("class_name", "")[:80]
    query = db.select(Student)
    if keyword:
        query = query.where(db.or_(Student.name.contains(keyword, autoescape=True),
                                   Student.student_no.contains(keyword, autoescape=True)))
    if selected_class:
        query = query.where(Student.class_name == selected_class)
    pagination = db.paginate(query.order_by(Student.student_no), per_page=20, max_per_page=20, error_out=False)
    classes = db.session.scalars(db.select(Student.class_name).distinct().order_by(Student.class_name)).all()
    return render_template("teacher/students.html", pagination=pagination, classes=classes,
                           keyword=keyword, selected_class=selected_class)


@bp.route("/students/<int:student_id>", methods=["GET", "POST"])
@role_required("teacher")
def edit_student(student_id):
    student = db.get_or_404(Student, student_id)
    history = db.session.scalars(db.select(StudentChange).where(StudentChange.student_id == student_id)
        .order_by(StudentChange.version.desc()).limit(50)).all()
    version = history[0].version if history else 0
    values = dict(request.form) if request.method == "POST" else {"name": student.name, "class_name": student.class_name}
    error, code = None, 200
    if request.method == "POST":
        try:
            if not version_matches(values.get("version"), version):
                raise ValueError("学生信息已更新，请刷新页面后重新核对并提交")
            name = clean_text(values.get("name", ""), "姓名", 80)
            class_name = clean_text(values.get("class_name", ""), "班级", 80)
            reason = clean_text(values.get("reason", ""), "修改原因", 300)
            if (name, class_name) == (student.name, student.class_name):
                raise ValueError("信息没有变化，无需保存")
            change = StudentChange(student_id=student.id, teacher_id=g.user.id, version=version + 1,
                old_name=student.name, new_name=name, old_class=student.class_name, new_class=class_name,
                reason=reason, created_at=current_app.config["NOW"]())
            db.session.add(change)
            student.name, student.class_name = name, class_name
            db.session.commit()
            flash("学生信息已更新；已发布任务的名单和历史考勤保持不变。", "success")
            return redirect(url_for("management.edit_student", student_id=student.id))
        except ValueError as exc:
            error, code = str(exc), 400
        except IntegrityError:
            db.session.rollback()
            error, code = "信息已被其他操作更新，请刷新页面后重试。", 409
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("保存学生信息失败")
            error, code = "保存失败，未应用本次修改，请稍后重试。", 500
    classes = db.session.scalars(db.select(Student.class_name).distinct().order_by(Student.class_name)).all()
    # Only the signed-in teacher's tasks are exposed from the shared student directory.
    tasks = db.session.scalars(db.select(AttendanceTask).join(TaskMember, TaskMember.task_id == AttendanceTask.id)
        .where(TaskMember.student_id == student_id, AttendanceTask.teacher_id == g.user.id)
        .order_by(AttendanceTask.created_at.desc())).all()
    return render_template("teacher/student_edit.html", student=student, values=values, version=version,
                           classes=classes, history=history, tasks=tasks, error=error), code


@bp.route("/tasks/<int:task_id>/students/<int:student_id>/attendance", methods=["GET", "POST"])
@role_required("teacher")
def adjust_attendance(task_id, student_id):
    task = db.get_or_404(AttendanceTask, task_id)
    if task.teacher_id != g.user.id:
        abort(403)
    if db.session.get(TaskMember, (task_id, student_id)) is None:
        abort(403)
    student = db.get_or_404(Student, student_id)
    history = db.session.scalars(db.select(AttendanceAdjustment).where(
        AttendanceAdjustment.task_id == task_id, AttendanceAdjustment.student_id == student_id)
        .order_by(AttendanceAdjustment.version.desc()).limit(50)).all()
    latest = history[0] if history else None
    version = latest.version if latest else 0
    original = db.session.scalar(db.select(AttendanceRecord).where(
        AttendanceRecord.task_id == task_id, AttendanceRecord.student_id == student_id))
    original_id = original.id if original else 0
    record = effective_record(task, student_id, original, latest)
    now = current_app.config["NOW"]()
    values = dict(request.form) if request.method == "POST" else {}
    error, code = None, 200
    if request.method == "POST":
        try:
            if not version_matches(values.get("version"), version) or not version_matches(values.get("original_id"), original_id):
                raise ValueError("签到状态已变化，请刷新页面后重新核对并提交")
            action = values.get("action", "")
            if action not in ACTION_LABELS:
                raise ValueError("请选择有效的调整操作")
            reason = clean_text(values.get("reason", ""), "调整原因", 300)
            if now < task.start_time:
                raise ValueError("任务尚未开始，不能调整签到状态")
            if action == "present" and record:
                raise ValueError("该学生已签到，无需补签")
            if action == "absent" and not record:
                raise ValueError("该学生当前没有有效签到，无需撤销")
            if action == "restore" and (not latest or latest.action == "restore"):
                raise ValueError("当前已是原始状态，无需恢复")
            db.session.add(AttendanceAdjustment(task_id=task_id, student_id=student_id,
                teacher_id=g.user.id, version=version + 1, action=action, reason=reason, created_at=now))
            db.session.commit()
            flash("签到状态已调整，学生端和考勤统计已同步更新。", "success")
            return redirect(url_for("management.adjust_attendance", task_id=task_id, student_id=student_id))
        except ValueError as exc:
            error, code = str(exc), 400
        except IntegrityError:
            db.session.rollback()
            error, code = "签到状态已被其他操作更新，请刷新页面后重试。", 409
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("调整签到状态失败")
            error, code = "保存失败，未应用本次调整，请稍后重试。", 500
    return render_template("teacher/attendance_edit.html", task=task, student=student, record=record,
        original=original, history=history, latest=latest, version=version, original_id=original_id,
        state=task_state(task, now), actions=ACTION_LABELS, values=values, error=error), code
