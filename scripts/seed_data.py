"""Fictional, repeatable local demo data. Existing passwords/tasks are never changed."""
from datetime import timedelta

from flask import current_app

from app import create_app
from extensions import db
from models import AttendanceRecord, AttendanceTask, Student, Teacher
from scripts.init_db import init_database
from services.attendance import freeze_roster

DEMO_PASSWORD = "Demo123!"


def seed_database():
    init_database()
    teachers = []
    for number, name in [("T001", "林老师"), ("T002", "周老师")]:
        teacher = db.session.scalar(db.select(Teacher).where(Teacher.teacher_no == number))
        if teacher is None:
            teacher = Teacher(teacher_no=number, name=name)
            teacher.set_password(DEMO_PASSWORD)
            db.session.add(teacher)
        teachers.append(teacher)
    students = []
    for index, name in enumerate(["陈小禾", "李星河", "王予安", "赵知夏", "孙远山",
                                  "钱沐风", "吴清和", "郑云舟", "冯书言", "蒋若宁"], 1):
        number = f"S{index:03}"
        student = db.session.scalar(db.select(Student).where(Student.student_no == number))
        if student is None:
            student = Student(student_no=number, name=name, class_name="软件一班" if index <= 5 else "软件二班")
            student.set_password(DEMO_PASSWORD)
            db.session.add(student)
        students.append(student)
    db.session.flush()
    now = current_app.config["NOW"]()
    created = 0
    expired = 0
    for index, teacher in enumerate(teachers):
        class_name = "软件一班" if index == 0 else "软件二班"
        for label, start, end in [("进行中", -1, 2), ("未开始", 24, 25), ("已结束", -25, -24)]:
            title = f"[演示] {class_name} Python 实训 · {label}"
            task = db.session.scalar(db.select(AttendanceTask).where(
                AttendanceTask.teacher_id == teacher.id, AttendanceTask.title == title))
            if task is not None:
                expired += task.end_time < now
                continue
            task = AttendanceTask(title=title, teacher_id=teacher.id, target_class_name=class_name,
                                  start_time=now + timedelta(hours=start), end_time=now + timedelta(hours=end),
                                  center_latitude=39.9042, center_longitude=116.4074, radius_meters=200,
                                  created_at=now)
            db.session.add(task)
            db.session.flush()
            freeze_roster(task, now)
            created += 1
            if label == "已结束":
                for student in students[index * 5:index * 5 + 2]:
                    if student.class_name == class_name:
                        db.session.add(AttendanceRecord(task_id=task.id, student_id=student.id,
                            checkin_time=task.start_time + timedelta(minutes=10), latitude=39.9042,
                            longitude=116.4074, distance_meters=0, status="success"))
    db.session.commit()
    return created, expired


def main():
    with create_app().app_context():
        created, expired = seed_database()
        print(f"演示数据准备完成，新建任务 {created} 个。账号、已有密码和任务未覆盖。")
        print("新建演示账号密码 Demo123!；T001/T002；S001–S010。仅限本地演示。")
        print("示例坐标为合成演示位置。真实定位演示请由教师重新获取当前位置创建任务。")
        if expired:
            print(f"已有 {expired} 个演示任务已结束；如需当前签到，请教师重新创建任务，不会自动修改旧时间。")


if __name__ == "__main__":
    main()
