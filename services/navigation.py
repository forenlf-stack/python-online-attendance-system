"""Rebuild return links from known local routes, never from arbitrary URLs."""


def directory_context(values):
    try:
        page = max(1, min(int(values.get("page", 1)), 100000))
    except (TypeError, ValueError):
        page = 1
    return {"q": values.get("q", "").strip()[:80],
            "class_name": values.get("class_name", "")[:80], "page": page}


def task_context(values):
    state = values.get("state", "全部")
    return {"q": values.get("q", "").strip()[:100],
            "state": state if state in ("全部", "进行中", "未开始", "已结束") else "全部"}
