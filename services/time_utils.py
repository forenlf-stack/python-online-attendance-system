"""Database values are naive UTC; form/display values are Beijing time."""
from datetime import datetime, timedelta, timezone

BEIJING = timezone(timedelta(hours=8))


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_beijing(value):
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is not None or "T" not in value:
            raise ValueError
        return parsed.replace(tzinfo=BEIJING).astimezone(timezone.utc).replace(tzinfo=None)
    except (ValueError, TypeError, OverflowError):
        raise ValueError("请输入有效的北京时间") from None


def beijing_time(value, form=False):
    if value is None:
        return "—"
    local = value.replace(tzinfo=timezone.utc).astimezone(BEIJING)
    return local.strftime("%Y-%m-%dT%H:%M" if form else "%Y-%m-%d %H:%M:%S")


def task_state(task, now):
    if now < task.start_time:
        return "未开始"
    if now > task.end_time:
        return "已结束"
    return "进行中"
