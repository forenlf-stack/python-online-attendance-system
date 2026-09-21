from datetime import timedelta

import pytest

from conftest import NOW, checkin, csrf_token, login
from extensions import db
from models import AttendanceTask


def task_form(client, **overrides):
    data = dict(csrf_token=csrf_token(client), title="课堂签到", target_class_name="一班",
        start_time="2026-09-21T12:00", end_time="2026-09-21T13:00",
        center_latitude="39.9042", center_longitude="116.4074", radius_meters="200")
    data.update(overrides)
    return data


def test_create_and_beijing_conversion(client, app):
    login(client, "teacher", "T1")
    assert client.get("/teacher/tasks/new").status_code == 200
    response = client.post("/teacher/tasks/new", data=task_form(client, teacher_id="2"))
    assert response.status_code == 302
    assert client.get(response.location).status_code == 200
    with app.app_context():
        task = db.session.get(AttendanceTask, 3)
        assert task.teacher_id == 1 and task.start_time == NOW
        assert task.end_time == NOW + timedelta(hours=1)
        assert task.radius_meters == 200


@pytest.mark.parametrize("overrides", [
    {"title":" "}, {"title":"x"*101}, {"target_class_name":"不存在"},
    {"start_time":""}, {"end_time":"bad"}, {"end_time":"2026-09-21T12:00"},
    {"end_time":"2026-09-20T12:00"}, {"start_time":"2026-09-21T12:00+08:00"},
    {"center_latitude":"91"}, {"center_latitude":"-91"}, {"center_longitude":"181"},
    {"center_longitude":"-181"}, {"center_latitude":"NaN"}, {"center_longitude":"Infinity"},
    {"center_latitude":""}, {"center_longitude":"bad"}, {"radius_meters":"0"},
    {"radius_meters":"-1"}, {"radius_meters":"NaN"}, {"radius_meters":"Infinity"},
    {"radius_meters":""}, {"radius_meters":"bad"},
])
def test_invalid_task_rejected(client, app, overrides):
    login(client, "teacher", "T1")
    assert client.post("/teacher/tasks/new", data=task_form(client, **overrides)).status_code == 400
    with app.app_context():
        assert db.session.query(AttendanceTask).count() == 2


@pytest.mark.parametrize("offset,label", [(-2,"未开始"), (0,"未签到"), (2,"缺勤")])
def test_roster_stats_and_states(client, app, offset, label):
    login(client)
    assert checkin(client).status_code == 200
    app.config["NOW"] = lambda: NOW + timedelta(hours=offset)
    login(client, "teacher", "T1")
    html = client.get("/teacher/tasks/1").get_data(as_text=True)
    assert 'id="expected-count">2<' in html
    assert 'id="signed-count">1<' in html
    assert 'id="missing-count">1<' in html
    assert label in html and "已签到" in html
    assert "S1" in html and "S2" in html and "S3" not in html


def test_user_text_is_escaped(client):
    login(client, "teacher", "T1")
    response = client.post("/teacher/tasks/new", data=task_form(client, title='<script>alert(1)</script>'))
    html = client.get(response.location).get_data(as_text=True)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html
