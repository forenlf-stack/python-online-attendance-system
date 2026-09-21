"""Non-destructive initialization; create_all is not a migration mechanism."""
from sqlalchemy import inspect

from app import create_app
from extensions import db
import models  # Register original and management tables.
from flask import current_app
from services.attendance import freeze_roster


def init_database():
    inspector = inspect(db.engine)
    # Refuse known incompatible existing tables before creating anything.
    for name, table in db.metadata.tables.items():
        if not inspector.has_table(name):
            continue
        existing = {column["name"] for column in inspector.get_columns(name)}
        missing = set(table.columns.keys()) - existing
        if missing:
            raise RuntimeError(f"表 {name} 缺少字段 {sorted(missing)}；请备份后迁移，初始化不会改表或删库。")
        for constraint in table.constraints:
            if isinstance(constraint, db.UniqueConstraint):
                required = set(constraint.columns.keys())
                actual = [set(item["column_names"]) for item in inspector.get_unique_constraints(name)]
                actual += [set(item["column_names"]) for item in inspector.get_indexes(name) if item["unique"]]
                if required not in actual:
                    raise RuntimeError(f"表 {name} 缺少唯一约束 {sorted(required)}；请备份后迁移。")
        for foreign_key in table.foreign_keys:
            if not any(foreign_key.parent.name in item["constrained_columns"]
                       and item["referred_table"] == foreign_key.column.table.name
                       for item in inspector.get_foreign_keys(name)):
                raise RuntimeError(f"表 {name} 缺少外键约束；请备份后迁移。")
    db.create_all()
    for task in db.session.scalars(db.select(models.AttendanceTask)).all():
        freeze_roster(task, current_app.config["NOW"]())
    db.session.commit()


def main():
    with create_app().app_context():
        init_database()
        print("数据库初始化完成；保留所有已有数据。")


if __name__ == "__main__":
    main()
