import sqlite3
from datetime import timedelta

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from conftest import NOW, checkin, csrf_token, login
from extensions import db
from models import AttendanceRecord, AttendanceTask
from services.geofence import calculate_distance


def count_records(app):
    with app.app_context():
        return db.session.query(AttendanceRecord).count()


def test_class_scope_and_missing_task(client, app):
    login(client)
    html = client.get("/student/").get_data(as_text=True)
    assert "任务1" in html and "任务2" not in html and "可以签到" in html
    assert checkin(client, 2).status_code == 403
    assert checkin(client, 999).status_code == 404
    assert count_records(app) == 0


def test_server_trust_and_personal_records(client, app):
    login(client)
    result = checkin(client, payload={"latitude":0,"longitude":0.0001,"student_id":2,
                                     "role":"teacher","distance":999,"inside":False,"success":False,
                                     "checkin_time":"2000-01-01"})
    assert result.status_code == 200 and result.json["success"]
    with app.app_context():
        record = db.session.scalar(db.select(AttendanceRecord))
        assert record.student_id == 1 and record.checkin_time == NOW and record.status == "success"
        assert record.latitude == 0 and record.longitude == 0.0001
        assert record.distance_meters == pytest.approx(calculate_distance(0,0,0,0.0001))
    assert "已签到" in client.get("/student/").get_data(as_text=True)
    assert "任务1" in client.get("/student/records").get_data(as_text=True)
    login(client, account="S2")
    assert "任务1" not in client.get("/student/records?student_id=1").get_data(as_text=True)
    assert client.get("/student/records/1").status_code == 404


def test_outside_then_retry_then_duplicate(client, app):
    login(client)
    response = checkin(client, payload={"latitude":0,"longitude":1,"inside":True,"distance":0,"success":True})
    assert response.status_code == 400
    assert "允许半径 100 米" in response.json["message"] and "超出约" in response.json["message"]
    assert count_records(app) == 0
    assert checkin(client).status_code == 200
    response = checkin(client)
    assert response.status_code == 409 and response.json["message"] == "你已签到，请勿重复提交"
    assert count_records(app) == 1


@pytest.mark.parametrize("seconds,status", [(-3601,400), (-3600,200), (0,200), (3600,200), (3601,400)])
def test_time_boundaries(client, app, seconds, status):
    app.config["NOW"] = lambda: NOW + timedelta(seconds=seconds)
    login(client)
    assert checkin(client).status_code == status
    assert count_records(app) == (status == 200)


@pytest.mark.parametrize("payload", [
    {}, {"latitude":"","longitude":0}, {"latitude":None,"longitude":0},
    {"latitude":True,"longitude":0}, {"latitude":[],"longitude":0},
    {"latitude":{},"longitude":0}, {"latitude":"NaN","longitude":0},
    {"latitude":float("nan"),"longitude":0}, {"latitude":"Infinity","longitude":0},
    {"latitude":float("inf"),"longitude":0}, {"latitude":0,"longitude":"-Infinity"},
    {"latitude":91,"longitude":0}, {"latitude":-91,"longitude":0},
    {"latitude":0,"longitude":181}, {"latitude":0,"longitude":-181},
    {"latitude":"bad","longitude":0}, [], "bad", 1,
])
def test_invalid_coordinates(client, app, payload):
    login(client)
    assert checkin(client, payload=payload).status_code == 400
    assert count_records(app) == 0


def test_malformed_json(client, app):
    login(client)
    result = client.post("/student/tasks/1/checkin", data="{broken", content_type="application/json",
                         headers={"X-CSRFToken":csrf_token(client)})
    assert result.status_code == 400 and count_records(app) == 0


@pytest.mark.parametrize("radius_delta,status", [(0,200), (-0.00001,400), (0.00001,200)])
def test_distance_exact_boundary_not_rounded(client, app, radius_delta, status):
    distance = calculate_distance(0,0,0,0.001)
    with app.app_context():
        db.session.get(AttendanceTask,1).radius_meters = distance + radius_delta
        db.session.commit()
    login(client)
    assert checkin(client, payload={"latitude":0,"longitude":0.001}).status_code == status


def test_real_database_unique_and_rollback(client, app):
    login(client)
    assert checkin(client).status_code == 200
    with app.app_context():
        db.session.add(AttendanceRecord(task_id=1,student_id=1,checkin_time=NOW,latitude=0,longitude=0,distance_meters=0))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        assert db.session.query(AttendanceRecord).count() == 1


def test_concurrent_duplicate_path(client, app, monkeypatch):
    login(client)
    original = Session.commit
    raced = False

    def race_commit(session):
        nonlocal raced
        pending = [r for r in session.new if isinstance(r, AttendanceRecord)]
        if pending and not raced:
            raced = True
            r = pending[0]
            # Another real database connection wins the insert after the route precheck.
            with Session(db.engine) as other:
                other.add(AttendanceRecord(task_id=r.task_id, student_id=r.student_id,
                    checkin_time=r.checkin_time, latitude=r.latitude, longitude=r.longitude,
                    distance_meters=r.distance_meters))
                original(other)
        return original(session)

    monkeypatch.setattr(Session, "commit", race_commit)
    response = checkin(client)
    assert response.status_code == 409 and "你已签到" in response.json["message"]
    assert count_records(app) == 1
    login(client, account="S2")
    assert checkin(client).status_code == 200


@pytest.mark.parametrize("error", [IntegrityError("insert",{},sqlite3.IntegrityError("FOREIGN KEY constraint failed")),
                                   OperationalError("insert",{},sqlite3.OperationalError("disk I/O error"))])
def test_other_database_errors_not_duplicates(client, app, monkeypatch, error):
    login(client)
    def fail(_):
        raise error
    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", fail)
        response = checkin(client)
    assert response.status_code == 500 and "保存失败" in response.json["message"]
    assert count_records(app) == 0
    assert checkin(client).status_code == 200
