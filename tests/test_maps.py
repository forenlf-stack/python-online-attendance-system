from html.parser import HTMLParser

from conftest import NOW, checkin, login
from extensions import db
from models import AttendanceRecord, AttendanceTask


class MapMarkup(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.maps = []
        self.scripts = []
        self.positions = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if tag == "details" and "fence-map" in data.get("class", "").split():
            self.maps.append(data)
        if tag == "script" and "src" in data:
            self.scripts.append(data["src"])
        if tag == "option" and "data-latitude" in data:
            self.positions.append(data)


def test_student_map_centers_are_scoped_to_class(client, app):
    with app.app_context():
        other = db.session.get(AttendanceTask, 2)
        other.center_latitude, other.center_longitude = 23.5, 45.5
        db.session.add(AttendanceRecord(task_id=1, student_id=2, checkin_time=NOW,
                        latitude=0, longitude=0.0005, distance_meters=55.6))
        db.session.commit()
    login(client)
    page = client.get("/student/")
    html = page.get_data(as_text=True)
    markup = MapMarkup(html)
    assert len(markup.maps) == 1
    assert float(markup.maps[0]["data-latitude"]) == 0
    assert float(markup.maps[0]["data-radius"]) == 100
    assert "open" not in markup.maps[0]  # No initial background tile requests.
    assert "23.5" not in html and "45.5" not in html
    assert "0.0005" not in html and not markup.positions  # Another student's location is private.
    assert all(src.startswith("/static/") for src in markup.scripts)
    assert page.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_teacher_result_map_has_only_owned_task_records(client, app):
    with app.app_context():
        db.session.add_all([
            AttendanceRecord(task_id=1, student_id=1, checkin_time=NOW,
                latitude=0, longitude=0.0004, distance_meters=44.48),
            AttendanceRecord(task_id=2, student_id=3, checkin_time=NOW,
                latitude=0, longitude=0.0008, distance_meters=88.96),
        ])
        db.session.commit()
    login(client, "teacher", "T1")
    html = client.get("/teacher/tasks/1").get_data(as_text=True)
    markup = MapMarkup(html)
    assert len(markup.maps) == 1 and len(markup.positions) == 1
    assert float(markup.positions[0]["data-longitude"]) == 0.0004
    assert "0.0008" not in html
    assert client.get("/teacher/tasks/2").status_code == 403


def test_creation_preview_does_not_change_backend_validation(client, app):
    from test_teacher import task_form
    login(client, "teacher", "T1")
    page = client.get("/teacher/tasks/new")
    markup = MapMarkup(page.get_data(as_text=True))
    assert markup.maps[0]["data-form"] == "true"
    assert "open" in markup.maps[0]
    response = client.post("/teacher/tasks/new", data=task_form(client, center_latitude="NaN"))
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert "map-placeholder" in html and "map-retry" in html
    assert "map-diagram" not in html and "本地示意图" not in html
    with app.app_context():
        assert db.session.query(AttendanceTask).count() == 2


def test_map_assets_are_local_and_served(client):
    for name in ["vendor/leaflet/leaflet.js", "vendor/leaflet/leaflet.css", "js/maps.js", "css/maps.css"]:
        response = client.get("/static/" + name)
        assert response.status_code == 200 and len(response.data) > 100
    assert client.get("/static/vendor/leaflet/LICENSE").status_code == 200
    assert "maps.js" not in client.get("/login").get_data(as_text=True)


def test_map_hints_cannot_bypass_fence_or_identity(client, app):
    login(client)
    result = checkin(client, payload={"latitude": 0, "longitude": 1,
        "map_inside": True, "radius_meters": 999999, "student_id": 2, "distance_meters": 0})
    assert result.status_code == 400
    with app.app_context():
        assert db.session.query(AttendanceRecord).count() == 0
    assert checkin(client).status_code == 200
