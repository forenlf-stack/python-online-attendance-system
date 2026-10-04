import csv
import io
from html.parser import HTMLParser
from urllib.parse import urlsplit, parse_qs

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from conftest import NOW, checkin, csrf_token, login
from extensions import db
from models import AttendanceAdjustment, AttendanceTask, Student
from services.exports import csv_content
from test_management import student_form
from test_teacher import task_form


def test_csv_export_authorization(client):
    assert client.get('/teacher/tasks/1/export.csv').status_code == 302
    login(client)
    assert client.get('/teacher/tasks/1/export.csv').status_code == 403
    login(client, 'teacher', 'T2')
    assert client.get('/teacher/tasks/1/export.csv').status_code == 403
    assert client.get('/teacher/tasks/999/export.csv').status_code == 404


def test_export_matches_effective_roster_and_no_fake_location(client, app):
    login(client)
    assert checkin(client).status_code == 200
    with app.app_context():
        db.session.add_all([
            AttendanceAdjustment(task_id=1, student_id=1, teacher_id=1, version=1,
                                 action='absent', reason='核实撤销', created_at=NOW),
            AttendanceAdjustment(task_id=1, student_id=2, teacher_id=1, version=1,
                                 action='present', reason='核实补签', created_at=NOW),
        ])
        db.session.get(Student, 1).class_name = '已转班'
        db.session.commit()
    login(client, 'teacher', 'T1')
    response = client.get('/teacher/tasks/1/export.csv?q=学生2&attendance=signed')
    assert response.status_code == 200 and response.data.startswith(b'\xef\xbb\xbf')
    assert 'attachment' in response.headers['Content-Disposition']
    assert response.headers['Cache-Control'] == 'no-store'
    rows = list(csv.reader(io.StringIO(response.data.decode('utf-8-sig'))))
    assert len(rows) == 3  # Export always contains the full frozen roster.
    assert rows[1][2:6] == ['S1', '学生1', '已转班', '未签到']
    assert rows[1][6:] == ['', '', '']
    assert rows[2][5:] == ['已签到', '教师补签', '2026-09-21 12:00:00', '']
    assert 'S3' not in response.get_data(as_text=True)


@pytest.mark.parametrize('value', ['=1+1', '+SUM(A1:A2)', '-1+1', '@SUM(A1)', '  =1+1', '\tformula', '\nformula'])
def test_csv_formula_cells_are_inert(value):
    rows = list(csv.reader(io.StringIO(csv_content([[value, 'a,"b"\nc', '普通中文']]).lstrip('\ufeff'))))
    assert rows == [["'" + value, 'a,"b"\nc', '普通中文']]


def test_export_quotes_names_and_task_text(client, app):
    with app.app_context():
        db.session.get(Student, 1).name = '=HYPERLINK("https://example.invalid")'
        db.session.get(AttendanceTask, 1).title = '中文,带引号"和换行\n任务'
        db.session.commit()
    login(client, 'teacher', 'T1')
    response = client.get('/teacher/tasks/1/export.csv')
    rows = list(csv.reader(io.StringIO(response.data.decode('utf-8-sig'))))
    assert len(rows) == 3 and rows[1][0] == '中文,带引号"和换行\n任务'
    assert rows[1][3].startswith("'=HYPERLINK")


def test_student_directory_return_context_survives_post(client):
    login(client, 'teacher', 'T1')
    path = '/teacher/students/1?q=S1&class_name=一班&page=2'
    response = client.post(path, data=student_form(client))
    assert response.status_code == 302
    query = parse_qs(urlsplit(response.location).query)
    assert query == {'q': ['S1'], 'class_name': ['一班'], 'page': ['2']}
    page = client.get(response.location).get_data(as_text=True)
    assert 'q=S1' in page and 'page=2' in page
    assert 'class_name=%E4%B8%80%E7%8F%AD' in page


def test_return_context_cannot_redirect_outside_app(client):
    login(client, 'teacher', 'T1')
    response = client.post('/teacher/students/1?next=https://example.invalid&page=bad&q=<script>', data=student_form(client))
    assert response.status_code == 302 and response.location.startswith('/teacher/students/1?')
    assert 'example.invalid' not in response.location
    assert parse_qs(urlsplit(response.location).query)['page'] == ['1']
    page = client.get('/teacher/tasks/1?q=<script>&state=bad&next=https://example.invalid').get_data(as_text=True)
    assert '<script>' not in page and 'example.invalid' not in page
    assert 'state=%E5%85%A8%E9%83%A8' in page


def test_creation_storage_error_keeps_form_without_partial_task(client, app, monkeypatch):
    login(client, 'teacher', 'T1')
    form = task_form(client, title='保存失败也保留此标题')
    def fail(_):
        raise OperationalError('commit', {}, Exception('simulated disk failure'))
    with monkeypatch.context() as patch:
        patch.setattr(Session, 'commit', fail)
        response = client.post('/teacher/tasks/new', data=form)
    assert response.status_code == 500 and '保存失败也保留此标题' in response.get_data(as_text=True)
    assert '任务未创建成功' in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.query(AttendanceTask).count() == 2
    assert client.post('/teacher/tasks/new', data=task_form(client)).status_code == 302


class Links(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.hrefs = set()
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            value = dict(attrs).get('href', '')
            if value.startswith('/') and not value.startswith('//'):
                self.hrefs.add(value.split('#')[0])


@pytest.mark.parametrize('role,account,paths', [
    ('teacher', 'T1', ['/teacher/', '/teacher/tasks/new', '/teacher/tasks/1', '/teacher/students',
                        '/teacher/students/1', '/teacher/tasks/1/students/1/attendance', '/help']),
    ('student', 'S1', ['/student/', '/student/records', '/help'])])
def test_role_page_links_lead_to_accessible_pages(client, role, account, paths):
    login(client, role, account)
    for path in paths:
        page = client.get(path)
        assert page.status_code == 200
        for link in Links(page.get_data(as_text=True)).hrefs:
            response = client.get(link, follow_redirects=True)
            assert response.status_code == 200, (path, link)
            assert '登录在线考勤' not in response.get_data(as_text=True)


def test_help_and_error_recovery_without_login(client):
    page = client.get('/help')
    assert page.status_code == 200 and '定位与网络' in page.get_data(as_text=True)
    error = client.get('/not-a-route')
    assert error.status_code == 404 and '查看使用帮助' in error.get_data(as_text=True)
