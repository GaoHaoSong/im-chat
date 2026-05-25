# IM Chat

局域网 Python + Vue 3 IM 网页聊天工具。

## 功能

- 用户名 + PIN 注册 / 登录 / 自动登录 / 退出登录
- 一对一实时聊天（文字 / 表情 / 图片 / 文件）
- 消息撤回（2 分钟内）、未读计数、时间戳、历史翻页
- @提及、引用回复
- 在线/离线分组（可折叠）
- PC 两栏 + 手机单栏切换布局

## 启动

### 方式一：本地 Python

```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 方式二：Docker Compose（推荐）

```bash
docker compose up -d --build
```

停止：

```bash
docker compose down
```

### 方式三：纯 Docker

```bash
docker build -t im-chat .
docker run -d --name im-chat -p 8000:8000 -v "$(pwd)/data:/app/data" --restart unless-stopped im-chat
```

浏览器访问 http://localhost:8000，局域网内其他设备访问 http://<你的IP>:8000。

### 数据持久化

宿主机 `./data/` 挂载到容器 `/app/data/`：

- `im.db` SQLite 数据库
- `uploads/` 上传的图片和文件

容器删了重建不会丢数据；升级版本只需重新 `docker compose up -d --build`，schema 自动迁移。

## 测试

```bash
pytest
```

## 目录结构

- `app/` Python 后端 + 静态前端
- `data/` 运行时数据（数据库 + 上传文件，不入库）
- `tests/` pytest 测试
