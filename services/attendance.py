"""Frozen task membership and effective attendance shared by both roles."""
from dataclasses import dataclass
from datetime import datetime

from extensions import db
from models import AttendanceAdjustment, AttendanceRecord, AttendanceTask, Student, TaskMember, TaskRoster

ACTION_LABELS = {"present": "教师补签", "absent": "撤销签到", "restore": "恢复原始状态"}


def freeze_roster(task, now):
    if db.session.get(TaskRoster, task.id) is not None:
        return
    # Include original records when upgrading: preserve evidence from former classmates.
    ids = set(db.session.scalars(db.select(Student.id).where(Student.class_name == task.target_class_name)))
    ids.update(db.session.scalars(db.select(AttendanceRecord.student_id).where(AttendanceRecord.task_id == task.id)))
    db.session.add(TaskRoster(task_id=task.id, frozen_at=now))
    db.session.add_all(TaskMember(task_id=task.id, student_id=student_id,
                                  class_name=task.target_class_name) for student_id in ids)


def latest_adjustments(task_id=None, student_id=None):
    query = db.select(AttendanceAdjustment)
    if task_id is not None:
        query = query.where(AttendanceAdjustment.task_id == task_id)
    if student_id is not None:
        query = query.where(AttendanceAdjustment.student_id == student_id)
    decisions = {}
    for item in db.session.scalars(query.order_by(AttendanceAdjustment.id)):
        decisions[item.task_id, item.student_id] = item
    return decisions


@dataclass
class EffectiveRecord:
    task: AttendanceTask
    student_id: int
    checkin_time: datetime
    source: str
    id: int
    latitude: float | None = None
    longitude: float | None = None
    distance_meters: float | None = None

    @property
    def has_location(self):
        return self.source == "location"


def effective_record(task, student_id, original, adjustment):
    if adjustment and adjustment.action == "absent":
        return None
    if adjustment and adjustment.action == "present":
        return EffectiveRecord(task, student_id, adjustment.created_at, "teacher", adjustment.id)
    if original:
        return EffectiveRecord(task, student_id, original.checkin_time, "location", original.id,
                               original.latitude, original.longitude, original.distance_meters)
    return None


def task_roster(task):
    students = db.session.scalars(db.select(Student).join(TaskMember, TaskMember.student_id == Student.id)
        .where(TaskMember.task_id == task.id).order_by(Student.student_no)).all()
    originals = {r.student_id: r for r in db.session.scalars(db.select(AttendanceRecord).where(
        AttendanceRecord.task_id == task.id))}
    adjustments = latest_adjustments(task_id=task.id)
    rows = [(s, effective_record(task, s.id, originals.get(s.id), adjustments.get((task.id, s.id))))
            for s in students]
    signed = sum(r is not None for _, r in rows)
    return rows, {"expected": len(rows), "signed": signed, "missing": len(rows) - signed}


def student_attendance(student_id):
    tasks = db.session.scalars(db.select(AttendanceTask).join(TaskMember, TaskMember.task_id == AttendanceTask.id)
        .where(TaskMember.student_id == student_id).order_by(AttendanceTask.created_at.desc())).all()
    originals = {r.task_id: r for r in db.session.scalars(db.select(AttendanceRecord).where(
        AttendanceRecord.student_id == student_id))}
    adjustments = latest_adjustments(student_id=student_id)
    return [(task, effective_record(task, student_id, originals.get(task.id), adjustments.get((task.id, student_id))),
             adjustments.get((task.id, student_id))) for task in tasks]
