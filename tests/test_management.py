import re
from datetime import timedelta

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app import create_app
from conftest import NOW, checkin, csrf_token, login
from extensions import db
from models import (AttendanceAdjustment, AttendanceRecord, AttendanceTask, Student,
                    StudentChange, TaskMember, TaskRoster, Teacher)
from scripts.init_db import init_database
from scripts.upgrade_management import upgrade_database
from services.attendance import task_roster
from test_teacher import task_form


def hidden(html, name):
    return re.search(r'name="' + name + r'" value="([^\"]*)"', html).group(1)


def adjustment_form(client, task_id=1, student_id=1, **overrides):
    page = client.get(f"/teacher/tasks/{task_id}/students/{student_id}/attendance").get_data(as_text=True)
    data = {name: hidden(page, name) for name in ("csrf_token", "version", "original_id")}
    data.update(action="present", reason="教师核实到场")
    data.update(overrides)
    return data


def student_form(client, student_id=1, **overrides):
    page = client.get(f"/teacher/students/{student_id}").get_data(as_text=True)
    data = {name: hidden(page, name) for name in ("csrf_token", "version")}
    data.update(name="学生1", class_name="二班", reason="教务转班")
    data.update(overrides)
    return data


def adjust(client, **overrides):
    return client.post('/teacher/tasks/1/students/1/attendance', data=adjustment_form(client, **overrides))


def test_management_auth_and_csrf(client):
    assert client.get('/teacher/students').status_code == 302
    login(client)
    assert client.get('/teacher/students').status_code == 403
    assert client.get('/teacher/students/1').status_code == 403
    assert client.post('/teacher/tasks/1/students/1/attendance', data={"csrf_token": csrf_token(client)}).status_code == 403
    login(client, 'teacher', 'T2')
    for method in (client.get, client.post):
        kwargs = {"data": {"csrf_token": csrf_token(client)}} if method == client.post else {}
        assert method('/teacher/tasks/1/students/1/attendance', **kwargs).status_code == 403
    login(client, 'teacher', 'T1')
    assert client.get('/teacher/tasks/1/students/3/attendance').status_code == 403
    assert client.post('/teacher/students/1', data={}).status_code == 400
    assert client.post('/teacher/tasks/1/students/1/attendance', data={}).status_code == 400
    assert client.get('/teacher/students/999').status_code == 404


def test_transfer_preserves_old_tasks_and_new_tasks_use_new_class(client, app):
    login(client)
    assert checkin(client).status_code == 200
    login(client, 'teacher', 'T1')
    assert client.post('/teacher/students/1', data=student_form(client)).status_code == 302
    with app.app_context():
        student = db.session.get(Student, 1)
        assert student.class_name == '二班' and student.check_password('test-pass')
        assert db.session.get(TaskMember, (1, 1)) and not db.session.get(TaskMember, (2, 1))
        assert task_roster(db.session.get(AttendanceTask, 1))[1] == {"expected": 2, "signed": 1, "missing": 1}
        change = db.session.scalar(db.select(StudentChange))
        assert (change.old_class, change.new_class, change.teacher_id) == ('一班', '二班', 1)
    response = client.post('/teacher/tasks/new', data=task_form(client, target_class_name='二班'))
    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(TaskMember, (3, 1)) and db.session.get(TaskMember, (3, 3))
    login(client)
    page = client.get('/student/').get_data(as_text=True)
    assert '任务1' in page and '任务2' not in page and '原班级任务' in page
    assert checkin(client, 2).status_code == 403
    assert checkin(client, 1).status_code == 409


def test_manual_attendance_visible_everywhere_without_fake_location(client, app):
    login(client, 'teacher', 'T1')
    assert adjust(client).status_code == 302
    with app.app_context():
        assert db.session.query(AttendanceRecord).count() == 0
        adjustment = db.session.scalar(db.select(AttendanceAdjustment))
        assert adjustment.teacher_id == 1 and adjustment.created_at == NOW
        record = task_roster(db.session.get(AttendanceTask, 1))[0][0][1]
        assert record.source == 'teacher' and record.latitude is None and record.distance_meters is None
    html = client.get('/teacher/tasks/1').get_data(as_text=True)
    assert 'id="signed-count">1<' in html and '教师补签' in html
    assert 'data-latitude="None"' not in html and '<option value="1" data-latitude=' not in html
    login(client)
    assert '已签到' in client.get('/student/').get_data(as_text=True)
    page = client.get('/student/records').get_data(as_text=True)
    assert '教师补签' in page and '无定位' in page and '教师核实到场' in page
    assert checkin(client).status_code == 409
    login(client, account='S2')
    assert '教师核实到场' not in client.get('/student/records').get_data(as_text=True)


def test_revoke_and_restore_preserves_original_coordinates(client, app):
    login(client)
    assert checkin(client, payload={"latitude": 0, "longitude": 0.0001}).status_code == 200
    login(client, 'teacher', 'T1')
    assert adjust(client, action='absent', reason='核实后撤销').status_code == 302
    with app.app_context():
        original = db.session.scalar(db.select(AttendanceRecord))
        assert original.longitude == 0.0001
        assert task_roster(db.session.get(AttendanceTask, 1))[1]['signed'] == 0
    login(client)
    assert '已撤销' in client.get('/student/').get_data(as_text=True)
    page = client.get('/student/records').get_data(as_text=True)
    assert '还没有签到记录' in page and '核实后撤销' in page
    assert checkin(client).status_code == 409
    login(client, 'teacher', 'T1')
    assert adjust(client, action='restore').status_code == 302
    with app.app_context():
        record = task_roster(db.session.get(AttendanceTask, 1))[0][0][1]
        assert record.longitude == 0.0001 and record.source == 'location'
        assert db.session.query(AttendanceAdjustment).count() == 2
    assert 'id="signed-count">1<' in client.get('/teacher/tasks/1').get_data(as_text=True)


def test_restore_manual_without_original_allows_student_checkin(client):
    login(client, 'teacher', 'T1')
    assert adjust(client).status_code == 302
    assert adjust(client, action='absent').status_code == 302
    assert adjust(client, action='restore').status_code == 302
    login(client)
    assert checkin(client).status_code == 200


@pytest.mark.parametrize('overrides', [{"name": " "}, {"name": "x"*81}, {"class_name": ""},
    {"class_name": "x"*81}, {"reason": ""}, {"reason": "x"*301}, {"name": "a\nb"}, {"version": "garbage"}])
def test_invalid_student_change(client, app, overrides):
    login(client, 'teacher', 'T1')
    assert client.post('/teacher/students/1', data=student_form(client, **overrides)).status_code == 400
    with app.app_context():
        assert db.session.get(Student, 1).class_name == '一班'
        assert db.session.query(StudentChange).count() == 0


@pytest.mark.parametrize('overrides', [{"action": "invalid"}, {"reason": ""}, {"reason": "x"*301},
    {"action": "absent"}, {"action": "restore"}, {"version": "-1"}, {"original_id": "100"}])
def test_invalid_adjustment(client, app, overrides):
    login(client, 'teacher', 'T1')
    assert adjust(client, **overrides).status_code == 400
    with app.app_context():
        assert db.session.query(AttendanceAdjustment).count() == 0


def test_started_and_expired_tasks(client, app):
    login(client, 'teacher', 'T1')
    form = adjustment_form(client)
    app.config['NOW'] = lambda: NOW - timedelta(hours=2)
    assert client.post('/teacher/tasks/1/students/1/attendance', data=form).status_code == 400
    app.config['NOW'] = lambda: NOW + timedelta(days=2)
    assert client.post('/teacher/tasks/1/students/1/attendance', data=form).status_code == 302
    assert adjust(client, action='present').status_code == 400
    assert adjust(client, action='absent').status_code == 302
    assert '缺勤' in client.get('/teacher/tasks/1').get_data(as_text=True)


def test_stale_forms_cannot_overwrite_changes(client, app):
    login(client, 'teacher', 'T1')
    stale = student_form(client)
    assert client.post('/teacher/students/1', data=stale).status_code == 302
    stale['class_name'] = '三班'
    assert client.post('/teacher/students/1', data=stale).status_code == 400
    old = adjustment_form(client)
    assert client.post('/teacher/tasks/1/students/1/attendance', data=old).status_code == 302
    old['action'] = 'absent'
    assert client.post('/teacher/tasks/1/students/1/attendance', data=old).status_code == 400
    with app.app_context():
        assert db.session.get(Student, 1).class_name == '二班'
        assert db.session.query(AttendanceAdjustment).count() == 1


def test_student_checkin_invalidates_teacher_form(client):
    login(client, 'teacher', 'T1')
    form = adjustment_form(client)
    # Preserve teacher cookie/session in its client, use an independent student client.
    student_client = client.application.test_client()
    login(student_client)
    assert checkin(student_client).status_code == 200
    assert client.post('/teacher/tasks/1/students/1/attendance', data=form).status_code == 400


def test_directory_search_scope_and_escaping(client):
    login(client, 'teacher', 'T1')
    page = client.get('/teacher/students?q=S3&class_name=二班').get_data(as_text=True)
    assert '学生3' in page and '学生1' not in page
    assert '学生1' not in client.get('/teacher/students?q=%25').get_data(as_text=True)
    assert '任务2' not in client.get('/teacher/students/3').get_data(as_text=True)
    assert client.post('/teacher/students/1', data=student_form(client, name='<script>alert(1)</script>')).status_code == 302
    page = client.get('/teacher/students').get_data(as_text=True)
    assert '<script>alert(1)</script>' not in page and '&lt;script&gt;' in page
    assert adjust(client, reason='<img src=x onerror=alert(1)>').status_code == 302
    page = client.get('/teacher/tasks/1/students/1/attendance').get_data(as_text=True)
    assert '<img src=x' not in page and '&lt;img src=x' in page


def test_transaction_rollback(client, app, monkeypatch):
    login(client, 'teacher', 'T1')
    form = student_form(client)
    def fail(session):
        raise OperationalError('insert', {}, Exception('simulated I/O error'))
    with monkeypatch.context() as patch:
        patch.setattr(Session, 'commit', fail)
        assert client.post('/teacher/students/1', data=form).status_code == 500
    with app.app_context():
        assert db.session.get(Student, 1).class_name == '一班'
        assert db.session.query(StudentChange).count() == 0


def test_upgrade_legacy_backup_and_idempotence(tmp_path):
    app = create_app({'TESTING': True, 'NOW': lambda: NOW,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + (tmp_path/'legacy.db').as_posix()})
    with app.app_context():
        db.metadata.create_all(db.engine, tables=[Student.__table__, Teacher.__table__,
                                                 AttendanceTask.__table__, AttendanceRecord.__table__])
        teacher = Teacher(teacher_no='T1', name='老师', password_hash='preserve-teacher-hash')
        student = Student(student_no='S1', name='学生', class_name='一班', password_hash='preserve-student-hash')
        db.session.add_all([teacher, student]); db.session.flush()
        task = AttendanceTask(title='保留任务', teacher_id=teacher.id, target_class_name='一班',
            start_time=NOW-timedelta(hours=1), end_time=NOW+timedelta(hours=1),
            center_latitude=0, center_longitude=0, radius_meters=100)
        db.session.add(task); db.session.flush()
        db.session.add(AttendanceRecord(task_id=task.id, student_id=student.id,
            checkin_time=NOW, latitude=0, longitude=0, distance_meters=0))
        db.session.commit()
        backup = upgrade_database()
        assert backup and backup.exists()
        assert db.session.get(Student, student.id).password_hash == 'preserve-student-hash'
        assert db.session.get(TaskMember, (task.id, student.id))
        student.class_name = '二班'; db.session.commit()
        init_database()
        assert db.session.query(TaskMember).count() == 1
        assert db.session.query(TaskRoster).count() == 1
        assert task_roster(task)[1]['signed'] == 1
        db.session.remove(); db.engine.dispose()
