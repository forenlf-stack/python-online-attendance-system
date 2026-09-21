import re
from datetime import datetime, timedelta

import pytest

from app import create_app
from extensions import db
from models import AttendanceTask, Student, Teacher
from services.attendance import freeze_roster

NOW = datetime(2026, 9, 21, 4, 0, 0)


def csrf_token(client, path="/login"):
    html = client.get(path).get_data(as_text=True)
    return re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)


def login(client, role="student", account="S1", password="test-pass"):
    return client.post("/login", data={"csrf_token": csrf_token(client), "role": role,
                                      "account": account, "password": password})


def checkin(client, task_id=1, payload=None, token=None):
    return client.post(f"/student/tasks/{task_id}/checkin", json=payload if payload is not None else {
        "latitude": 0, "longitude": 0}, headers={"X-CSRFToken": token or csrf_token(client)})


@pytest.fixture
def app(tmp_path):
    app = create_app({"TESTING": True, "SECRET_KEY": "test-only-key", "NOW": lambda: NOW,
                      "SQLALCHEMY_DATABASE_URI": "sqlite:///" + (tmp_path / "test.db").as_posix()})
    with app.app_context():
        db.create_all()
        for index in (1, 2):
            teacher = Teacher(id=index, teacher_no=f"T{index}", name=f"教师{index}")
            teacher.set_password("test-pass")
            db.session.add(teacher)
        for index, cls in [(1, "一班"), (2, "一班"), (3, "二班")]:
            student = Student(id=index, student_no=f"S{index}", name=f"学生{index}", class_name=cls)
            student.set_password("test-pass")
            db.session.add(student)
        db.session.flush()
        for index, teacher_id, cls in [(1, 1, "一班"), (2, 2, "二班")]:
            db.session.add(AttendanceTask(id=index, title=f"任务{index}", teacher_id=teacher_id,
                target_class_name=cls, start_time=NOW-timedelta(hours=1), end_time=NOW+timedelta(hours=1),
                center_latitude=0, center_longitude=0, radius_meters=100, created_at=NOW))
        db.session.flush()
        for task in db.session.scalars(db.select(AttendanceTask)).all():
            freeze_roster(task, NOW)
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()
