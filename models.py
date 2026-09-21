from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db
from services.time_utils import utc_now


class PasswordMixin:
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Student(PasswordMixin, db.Model):
    __tablename__ = "student"
    id = db.Column(db.Integer, primary_key=True)
    student_no = db.Column(db.String(32), unique=True, nullable=False)
    name = db.Column(db.String(80), nullable=False)
    class_name = db.Column(db.String(80), nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)


class Teacher(PasswordMixin, db.Model):
    __tablename__ = "teacher"
    id = db.Column(db.Integer, primary_key=True)
    teacher_no = db.Column(db.String(32), unique=True, nullable=False)
    name = db.Column(db.String(80), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)


class AttendanceTask(db.Model):
    __tablename__ = "attendance_task"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teacher.id"), nullable=False, index=True)
    target_class_name = db.Column(db.String(80), nullable=False, index=True)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    center_latitude = db.Column(db.Float, nullable=False)
    center_longitude = db.Column(db.Float, nullable=False)
    radius_meters = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    teacher = db.relationship("Teacher")
    __table_args__ = (
        db.CheckConstraint("start_time < end_time", name="ck_task_time"),
        db.CheckConstraint("radius_meters > 0", name="ck_task_radius"),
        db.CheckConstraint("center_latitude BETWEEN -90 AND 90", name="ck_task_lat"),
        db.CheckConstraint("center_longitude BETWEEN -180 AND 180", name="ck_task_lon"),
    )


class AttendanceRecord(db.Model):
    __tablename__ = "attendance_record"
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("attendance_task.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False, index=True)
    checkin_time = db.Column(db.DateTime, nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    distance_meters = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(16), nullable=False, default="success")
    task = db.relationship("AttendanceTask")
    student = db.relationship("Student")
    __table_args__ = (
        db.UniqueConstraint("task_id", "student_id", name="uq_task_student"),
        db.CheckConstraint("status = 'success'", name="ck_record_success"),
    )

class TaskRoster(db.Model):
    """Marks even an empty task roster as frozen."""
    __tablename__ = "task_roster"
    task_id = db.Column(db.Integer, db.ForeignKey("attendance_task.id"), primary_key=True)
    frozen_at = db.Column(db.DateTime, nullable=False, default=utc_now)


class TaskMember(db.Model):
    __tablename__ = "task_member"
    task_id = db.Column(db.Integer, db.ForeignKey("attendance_task.id"), primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), primary_key=True)
    class_name = db.Column(db.String(80), nullable=False)


class StudentChange(db.Model):
    __tablename__ = "student_change"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False, index=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teacher.id"), nullable=False)
    version = db.Column(db.Integer, nullable=False)
    old_name = db.Column(db.String(80), nullable=False)
    new_name = db.Column(db.String(80), nullable=False)
    old_class = db.Column(db.String(80), nullable=False)
    new_class = db.Column(db.String(80), nullable=False)
    reason = db.Column(db.String(300), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    teacher = db.relationship("Teacher")
    __table_args__ = (db.UniqueConstraint("student_id", "version", name="uq_student_change_version"),)


class AttendanceAdjustment(db.Model):
    """Append-only decisions; original geolocation evidence is never overwritten."""
    __tablename__ = "attendance_adjustment"
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("attendance_task.id"), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False, index=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teacher.id"), nullable=False)
    version = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(16), nullable=False)
    reason = db.Column(db.String(300), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    teacher = db.relationship("Teacher")
    task = db.relationship("AttendanceTask")
    student = db.relationship("Student")
    __table_args__ = (
        db.UniqueConstraint("task_id", "student_id", "version", name="uq_adjustment_version"),
        db.CheckConstraint("action IN ('present', 'absent', 'restore')", name="ck_adjustment_action"),
    )
