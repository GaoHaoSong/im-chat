# 局域网 IM 网页聊天工具 · 设计文档

- 日期：2026-05-23
- 状态：待评审

## 1. 目标与范围

构建一个部署在局域网内、通过浏览器使用的实时聊天工具，支持 PC 与手机访问，参考 QQ 聊天面板的交互。

**包含功能**：
- 用户注册 / 登录（用户名 + PIN）/ 自动登录 / 退出登录
- 一对一实时文字聊天
- 表情（Emoji 面板）、图片发送、文件发送
- 消息撤回（2 分钟内）、未读计数、时间戳、历史翻页、@提及、引用回复
- 在线 / 离线分组列表，可折叠展开
- PC 端两栏布局，手机端单栏切换

**明确不包含**：群聊、好友关系管理、自定义分组、跨设备多端同时在线、注销账号、音视频、PWA / 原生 APP、跨浏览器兼容（仅现代浏览器）。

## 2. 决策摘要（澄清问答）

| 项 | 决策 | 备注 |
|---|---|---|
| 部署 | 局域网内单机部署 | |
| 数据持久化 | SQLite 全持久化（用户 + 消息） | |
| 认证 | 用户名 + PIN（4-6 位数字） | 浏览器记住 token 自动登录 |
| 分组 | 仅"在线 / 离线"两组，可折叠 | |
| 聊天功能 | 文字、表情、图片、文件、撤回、未读、时间戳、历史翻页、@提及、引用 | |
| 技术栈 | FastAPI + Vue 3 (CDN) + 原生 CSS | 单进程部署 |
| 多端登录 | 单会话（后登录踢掉先登录） | |
| 退出登录 | 支持，主动登出清除 token | |
| 移动端 | 响应式适配，单栏切换 | |

## 3. 整体架构

**单进程部署**：Python 进程（FastAPI + Uvicorn）监听一个端口，同时提供静态文件、HTTP API 与 WebSocket。

**数据存储**：
- SQLite 单文件（`data/im.db`）：用户、消息、会话
- 本地文件系统（`data/uploads/`）：图片、文件原件，数据库只存元数据

**进程内状态**：在线 WebSocket 连接表 `{username: WebSocket}`，重启即清空。

**目录结构**：
```
hello/
├── app/
│   ├── main.py           FastAPI 入口
│   ├── db.py             SQLite 连接与初始化
│   ├── models.py         数据库表定义
│   ├── auth.py           注册、登录、PIN 校验、token
│   ├── ws.py             WebSocket 处理 + 连接管理
│   ├── messages.py       发送、历史、撤回、@提及
│   ├── files.py          文件 / 图片上传下载
│   └── static/
│       ├── index.html
│       ├── app.js        Vue 3 应用
│       └── style.css
├── data/                 运行时生成
│   ├── im.db
│   └── uploads/
├── tests/
├── requirements.txt
└── README.md
```

## 4. 数据模型

### `users` 表
| 字段 | 类型 | 说明 |
|---|---|---|
| username | TEXT PRIMARY KEY | 用户名 |
| pin_hash | TEXT | bcrypt 哈希 |
| display_name | TEXT | 昵称 |
| created_at | INTEGER | 注册时间戳（秒） |
| last_seen_at | INTEGER | 最后在线时间戳 |
| read_state | TEXT | JSON `{"alice": <ts>, ...}` 记录与各用户最后一次已读时间 |

### `messages` 表
| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PRIMARY KEY AUTOINCREMENT | 消息 ID |
| from_user | TEXT | 发送者 username |
| to_user | TEXT | 接收者 username |
| kind | TEXT | `text` / `image` / `file` |
| content | TEXT | 文字内容；图片/文件存元数据 JSON |
| reply_to_id | INTEGER NULL | 引用消息 ID |
| mentions | TEXT NULL | JSON 数组 `["alice","bob"]` |
| created_at | INTEGER | 时间戳 |
| recalled | INTEGER | 0 / 1 |

索引：`(from_user, to_user, created_at)`、`(to_user, from_user, created_at)`。

### `sessions` 表
| 字段 | 类型 | 说明 |
|---|---|---|
| token | TEXT PRIMARY KEY | 32 字节随机 hex |
| username | TEXT | 关联用户 |
| created_at | INTEGER | 创建时间 |

### 未读计算

不单独建表，使用 `users.read_state`：未读数 = `messages` 中 `to_user=me AND from_user=peer AND created_at > read_state[peer]` 的数量。前端进入与某人的会话时调 `/api/messages/read` 更新该字段。

### 文件存储

文件保存为 `data/uploads/<uuid>_<原文件名>`。`messages.content` 存 `{"file_id":"...","name":"...","size":12345,"mime":"image/png"}`。

## 5. API 与 WebSocket 协议

### HTTP API

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/register` | `{username, pin, display_name}` → `{token}` |
| POST | `/api/login` | `{username, pin}` → `{token}` |
| POST | `/api/auto_login` | `{token}` → `{username, display_name}` 或 401 |
| POST | `/api/logout` | 删除当前 token 对应会话 |
| GET | `/api/users` | 全部用户列表（含在线状态、未读数） |
| GET | `/api/messages?peer=X&before=<msgId>&limit=30` | 拉取与 X 的历史消息（向前翻页） |
| POST | `/api/messages/read` | `{peer}` 标记已读 |
| POST | `/api/upload` | multipart 上传 → `{file_id, name, size, mime}` |
| GET | `/api/files/{file_id}` | 下载文件，图片返回 inline，其他 attachment |

认证：`Authorization: Bearer <token>` 头。

错误格式统一：`{"error":{"code":"...","message":"..."}}`。

### WebSocket

**端点**：`ws://host/ws?token=<token>`，连接时校验 token。

**连接生命周期**：
- 校验失败立即关闭
- 若该用户已有连接：旧连接收到 `{type:"kicked"}` 后关闭，新连接替换之
- 建立后广播 `{type:"presence", user, online:true}` 给其他在线用户

**客户端 → 服务端**：
```
{"type":"send", "to":"bob", "kind":"text"|"image"|"file", "content":"...", "reply_to_id":null|<id>, "mentions":[...]}
{"type":"recall", "message_id":<id>}
{"type":"ping"}
```

**服务端 → 客户端**：
```
{"type":"message", "message":{id, from_user, to_user, kind, content, reply_to_id, mentions, created_at}}
{"type":"recalled", "message_id":<id>, "by":"alice"}
{"type":"presence", "user":"bob", "online":true|false}
{"type":"kicked"}
{"type":"error", "code":"...", "message":"..."}
{"type":"pong"}
```

**撤回校验**：`from_user == 当前用户` 且 `now - created_at <= 120` 秒。

**乐观发送**：前端先用 tempId 渲染；收到服务端 `message` 帧后用真实 id 替换。

## 6. 前端结构与界面布局

### 视图切换

单页应用，无路由库，使用 Vue `v-if`：

- 启动 → 检查 localStorage.token → 有则 `/api/auto_login` → 成功进主视图，失败显示登录页
- 登录页内切换"登录 / 注册"
- 主视图 PC 端为左右两栏，手机端通过 `view: 'list' | 'chat'` 切换

### PC 主视图布局

```
┌──────────────────────┬──────────────────────────────────────────┐
│ [头像] 我 [⚙]        │ 与 bob 的对话           [bob 在线 ●]     │
│ ──────────────       │ ──────────────────────────────────────── │
│ ▼ 在线 (3)           │   昨天 14:32                              │
│  ● alice             │   [alice头像] 你好啊                      │
│  ● bob       [3]     │                14:35  [我头像] 在的       │
│  ● carol             │   今天 09:10                              │
│                      │   [alice头像] @我 看一下 [引用]            │
│ ▶ 离线 (5)           │   ┌─ image.png ──┐                       │
│                      │   │ (缩略图)      │                       │
│                      │   └──────────────┘                       │
│                      │ ──────────────────────────────────────── │
│                      │ [😀][📎图片][📁文件]                       │
│                      │ ┌────────────────────────────┐  [发送]    │
│                      │ │ 输入消息...                 │           │
│                      │ └────────────────────────────┘           │
└──────────────────────┴──────────────────────────────────────────┘
```

### 左侧用户列表

- "在线 / 离线"两个分组，组标题 `▼ / ▶` 折叠切换
- "在线"组首位是自己；右侧 `⚙` 菜单含"退出登录"
- 未读数显示为红色数字徽章
- 选中行高亮
- 切换会话时调 `/api/messages/read` 清除该会话未读

### 右侧聊天面板

- 顶部：对方昵称 + 在线状态灯
- 消息区：自动滚到底；上滑触发翻页
- 自己消息靠右（蓝底白字），对方靠左（白底）
- 时间分隔行：相邻两条间隔 > 5 分钟时显示
- 引用回复显示被引用消息缩略，点击定位
- @ 提及高亮显示
- 撤回：右键 / 长按出菜单，2 分钟内可撤
- 图片：缩略显示，点击放大
- 文件：图标 + 名称 + 大小，点击下载

### 工具条

- 😀 表情：弹出常用 emoji 面板（约 80 个）
- 📎 图片 / 📁 文件：调起选择器上传
- 输入框 `@` 触发在线用户提示选择
- 引用回复：选中消息后点击"引用"按钮设置 `reply_to_id`

### 移动端适配

断点：`@media (max-width: 768px)`。

```
列表页                       聊天页
┌─────────────────┐          ┌─────────────────┐
│ 我 [⚙]          │          │ ← bob   [在线 ●]│
├─────────────────┤          ├─────────────────┤
│ ▼ 在线 (3)      │          │   消息气泡...    │
│  ● alice    [2] │          │                 │
│  ● bob      [3] │          │                 │
│ ▶ 离线 (5)      │          ├─────────────────┤
└─────────────────┘          │ [😀][📎][📁]    │
                             │ [输入框  ][发]   │
                             └─────────────────┘
```

- 列表页点用户 → 切换到聊天页；聊天页 `←` 返回
- 用 `100dvh` 或监听 `visualViewport` resize，软键盘弹出时输入区不被遮挡
- 触摸目标最小 44×44px
- 长按 500ms 代替右键
- 图片支持双指缩放
- viewport：`width=device-width, initial-scale=1, viewport-fit=cover`

### 状态管理

Vue 3 reactive：`currentUser`、`users`、`activeChat`、`messages` Map、`unread` Map、`view`。WebSocket 单例挂 `window.__ws`，收消息按 `from_user / to_user` 路由到对应会话。

## 7. 关键流程

### 7.1 启动 / 自动登录

1. 读 `localStorage.token`
2. 有 → `/api/auto_login`；成功进主视图、建立 WebSocket；401 清 token 显示登录页
3. 无 → 登录页
4. 注册校验：username 3-20 字符（字母数字下划线），PIN 4-6 位数字；成功 → 写 users / sessions → 返回 token
5. 登录：bcrypt 校验 PIN → 生成新 token

### 7.2 发送文字

1. 前端乐观插入 `{tempId, status:'sending'}`
2. WebSocket 发 `send`
3. 服务端校验 token 用户与 from_user 一致 → 写库 → 推 `message` 给收发双方
4. 发送者用真实 id 替换 tempId
5. 接收者插入消息；非当前会话则递增 unread

### 7.3 发送图片 / 文件

1. POST `/api/upload`（multipart）→ 返回元数据
2. WebSocket 发 `send`，kind=image/file，content=元数据 JSON 字符串
3. 接收端渲染：图片直接 `<img src="/api/files/{file_id}">`；文件显示图标 + 名称 + 大小

### 7.4 撤回

1. 用户触发撤回 → WebSocket `recall`
2. 服务端校验作者 + 时间 → 更新 `recalled=1` → 推 `recalled` 给双方
3. 两端将消息替换为"XX 撤回了一条消息"

### 7.5 拉历史

1. 进入会话且 `messages[peer]` 为空 → `/api/messages?peer=X&limit=30`
2. 上滑触顶 → `/api/messages?peer=X&before=<最早id>&limit=30`
3. SQL：`WHERE (from_user=me AND to_user=peer) OR (from_user=peer AND to_user=me) ORDER BY created_at DESC LIMIT ?`，反转后插入消息列表前部

### 7.6 在线状态

1. WebSocket 连接建立 → 加入内存连接表 → 广播 `presence online`
2. 断开 → 移除连接表 → 更新 `users.last_seen_at` → 广播 `presence offline`
3. 心跳：前端 30 秒一次 `ping`，10 秒无 `pong` 视断线，自动重连

### 7.7 踢旧会话

1. 新连接 → 校验 token 取 username → 查连接表
2. 已有 → 旧连接发 `kicked` 后关闭 → 替换为新连接
3. 旧端显示"你已在其他设备登录"，不再自动重连

### 7.8 退出登录

1. 用户点击"退出登录" → 确认弹窗
2. POST `/api/logout`（带 token）
3. 服务端：删除 `sessions` 行；关闭 WebSocket 连接；广播 presence offline
4. 前端：清 localStorage、清内存、关 WebSocket、返回登录页
5. 后端请求失败也照样清本地状态（容错）

## 8. 错误处理

**前端**：
- WebSocket 断线 → 顶部 banner + 指数退避重连（1s → 2s → 5s → 10s → 30s 封顶）
- HTTP 失败 → toast 显示错误信息
- 上传：进度条 + 失败重试
- 收 `kicked` → 大面积提示 + 返回登录按钮，不再自动重连
- 收 `error` 帧 → 按 code 提示

**后端**：
- FastAPI 统一异常处理 → `{"error":{"code","message"}}`
- token 无效 401；权限不足 403；不存在 404；参数错误 422
- 文件上传：单文件最大 20MB，图片最大 10MB（超出 413）
- WebSocket 非法 JSON → 回 error 帧但不断连接
- SQLite：开启 WAL；写操作通过 `asyncio.Lock` 串行化

**边界**：
- 给自己发消息：允许（备忘录用途）
- 给离线用户发：正常入库
- 给不存在的用户：拒绝（404）
- 撤回他人消息：拒绝（403）
- @ 不存在的用户：静默忽略（按文本渲染）
- 同一文件多次上传：每次都存独立副本（不去重）

## 9. 测试策略

### 后端单元 / API（pytest + httpx）

- `test_auth.py`：注册成功 / 重名失败 / PIN 错误 / token 自动登录 / 退出后 token 失效
- `test_messages.py`：发文字 / 拉历史翻页 / 撤回成功 / 撤回超时失败 / 撤回他人失败 / @ 提及解析 / 引用回复
- `test_files.py`：上传成功 / 超限拒绝 / 下载 / 404
- `test_users.py`：用户列表含在线状态 / 未读数计算

每个测试用临时 SQLite 与临时 uploads 目录，独立 fixture。

### WebSocket 集成（pytest + FastAPI TestClient）

- 两个客户端 A、B 连接 → A 发 → B 收
- 同用户第二个连接 → 第一个收 kicked
- 断开 → 其他在线用户收 presence offline
- 退出登录 → token 后续无法用于建立 WebSocket

### 手动验收清单（README）

- 浏览器多标签模拟多用户实时收发
- PC + 手机视口（Chrome DevTools）布局正常
- 重启后端：历史在，用户重连恢复在线
- 图片、文件、表情、撤回、@、引用、退出登录各跑一遍

### 不覆盖

- 大规模并发压测（场景：局域网，几十人级）
- 跨浏览器兼容（仅 Chrome / Edge / Safari 最新版）
- 移动原生 APP（仅响应式 H5）

## 10. 依赖与运行

`requirements.txt`：
```
fastapi
uvicorn[standard]
bcrypt
python-multipart
aiosqlite
pytest
httpx
pytest-asyncio
```

启动：`python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`

数据目录运行时自动创建。
