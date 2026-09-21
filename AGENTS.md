# 项目开发规则

- 本机统一完成开发，无 A/B 分工限制。
- 使用 Python、Flask、Flask-SQLAlchemy、SQLite、Jinja2、原生 JavaScript、本地 CSS、pytest。
- 实现教师/学生登录、班级签到任务、圆形电子围栏、结果与个人记录。按最新需求允许 Leaflet + OpenStreetMap 展示范围和位置；按最新需求移除本地示意图，失败仅提示重试；不增加独立管理员后台、注册、AI 或复杂基础设施。
- 地图只展示、不决定签到成功，不加入地图选点或持续追踪；坐标保持 WGS-84。Leaflet 静态文件本地保存，OSM 保留署名、正常 Referer 与浏览器缓存，不批量下载或离线缓存瓦片。
- 独立学生表和教师表；原始定位表只保存成功签到，教师调整单独留痕；支持学生班级与姓名维护、任务固定名单、教师补签/撤销/恢复；数据库 UTC 无时区时间，输入/显示北京时间。
- 修改业务逻辑后运行相关测试，交付前运行全套测试。不得删除用户数据库或覆盖用户修改。
- Windows 项目根目录命令：`.\.venv\Scripts\python.exe -m scripts.init_db`、`.\.venv\Scripts\python.exe -m scripts.seed_data`、`.\.venv\Scripts\python.exe app.py`、`.\.venv\Scripts\python.exe -m pytest -q`。
