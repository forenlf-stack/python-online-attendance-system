import math
from datetime import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import create_app
from conftest import NOW
from extensions import db
from models import AttendanceRecord, AttendanceTask, Student, Teacher
from scripts.init_db import init_database
from scripts.seed_data import seed_database
from services.geofence import EARTH_RADIUS_METERS, calculate_distance
from services.time_utils import beijing_time, parse_beijing, utc_now


def test_haversine():
    assert calculate_distance(39.9,116.4,39.9,116.4) == 0
    assert calculate_distance(0,0,0,1) == pytest.approx(111194.92664455874)
    assert calculate_distance(0,0,0,0.0001) < 100
    assert calculate_distance(0,0,0,0.01) > 100
    assert calculate_distance(0,0,0,180) == pytest.approx(math.pi * EARTH_RADIUS_METERS)
    assert calculate_distance(0,179.999,0,-179.999) < 223
    assert calculate_distance(0,0,1,1) == calculate_distance(1,1,0,0)
    assert math.isfinite(calculate_distance(90,0,-90,180))
    with pytest.raises(ValueError):
        calculate_distance(float("nan"),0,0,0)


def test_time_conversion():
    assert parse_beijing("2026-09-21T12:00") == NOW
    assert parse_beijing("2026-01-01T00:00") == datetime(2025,12,31,16)
    assert beijing_time(NOW) == "2026-09-21 12:00:00"
    assert utc_now().tzinfo is None
    with pytest.raises(ValueError):
        parse_beijing("2026-09-21T12:00Z")


def test_foreign_keys_enabled(app):
    with app.app_context():
        assert db.session.execute(text("PRAGMA foreign_keys")).scalar() == 1
        db.session.add(AttendanceRecord(task_id=999,student_id=1,checkin_time=NOW,
                                       latitude=0,longitude=0,distance_meters=0))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_init_seed_repeatable_preserves_data(tmp_path):
    app = create_app({"TESTING":True,"NOW":lambda:NOW,
                      "SQLALCHEMY_DATABASE_URI":"sqlite:///"+(tmp_path/"seed.db").as_posix()})
    with app.app_context():
        init_database()
        init_database()
        assert seed_database() == (6,0)
        student = db.session.scalar(db.select(Student).where(Student.student_no == "S001"))
        student.set_password("changed-password")
        old_hash = student.password_hash
        task = db.session.scalar(db.select(AttendanceTask))
        old_time = task.end_time
        db.session.commit()
        assert seed_database() == (0,2)
        assert db.session.query(Teacher).count() == 2
        assert db.session.query(Student).count() == 10
        assert db.session.query(AttendanceTask).count() == 6
        assert db.session.query(AttendanceRecord).count() == 4
        assert student.password_hash == old_hash and student.check_password("changed-password")
        assert task.end_time == old_time
        assert {s.class_name for s in db.session.scalars(db.select(Student))} == {"软件一班","软件二班"}
        assert all(t.check_password("Demo123!") for t in db.session.scalars(db.select(Teacher)))
        db.session.remove()
        db.engine.dispose()


def test_incompatible_schema_is_not_destroyed(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI":"sqlite:///"+(tmp_path/"legacy.db").as_posix()})
    with app.app_context():
        db.session.execute(text("CREATE TABLE student (id INTEGER PRIMARY KEY, name TEXT)"))
        db.session.execute(text("INSERT INTO student VALUES (1, 'preserve')"))
        db.session.commit()
        with pytest.raises(RuntimeError, match="备份后迁移"):
            init_database()
        assert db.session.execute(text("SELECT name FROM student")).scalar() == "preserve"
        db.session.remove()
        db.engine.dispose()


def test_cookie_configuration(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("COOKIE_SECURE", raising=False)
    app = create_app()
    assert not app.config["SESSION_COOKIE_SECURE"] and not app.debug
    assert app.config["SESSION_COOKIE_HTTPONLY"] and app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert app.secret_key != create_app().secret_key
    monkeypatch.setenv("COOKIE_SECURE", "1")
    monkeypatch.setenv("SECRET_KEY", "environment-secret")
    secure_app = create_app()
    assert secure_app.config["SESSION_COOKIE_SECURE"] and secure_app.secret_key == "environment-secret"
