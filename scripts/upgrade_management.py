"""Back up SQLite, then add management tables and freeze existing task rosters."""
import sqlite3
from datetime import datetime
from pathlib import Path

from app import create_app
from extensions import db
from scripts.init_db import init_database


def upgrade_database():
    source = Path(db.engine.url.database).resolve()
    backup_path = None
    if source.exists():
        backup_dir = source.parent / "backups"
        backup_dir.mkdir(exist_ok=True)
        backup_path = backup_dir / f"attendance-before-management-{datetime.now():%Y%m%d-%H%M%S-%f}.db"
        with sqlite3.connect(source) as original, sqlite3.connect(backup_path) as backup:
            original.backup(backup)
    init_database()
    return backup_path


def main():
    with create_app().app_context():
        backup = upgrade_database()
        print(f"升级前备份：{backup}" if backup else "新数据库，无需旧库备份。")
        print("管理功能已升级：保留原始四表数据，补齐任务固定名单。")


if __name__ == "__main__":
    main()
