# 班级课表统计网站

> 项目简介：校内课表批量处理工具，支持导入本校 PDF 格式课表，自动解析并完成课表统计，可直接下载导出统计文件。无登录功能，**不保存上传的文件，无历史记录查询**。

## ✨ 功能特性

- 批量导入本校 PDF 课表文件
- 自动解析 PDF 内课程信息，汇总全班课表
- 自动统计全班共同空闲时间段
- 📥 导出统计结果为 CSV 表格，WPS/Excel 直接打开
- 响应式页面，电脑/手机均可访问
- 支持把已导出的 CSV 重新导入查看，无需重复解析 PDF

> ⚠️ 重要说明：本网站为纯工具站点，**无账号登录功能，不会在服务器存储上传的 PDF 文件，不提供历史文件查询**，文件仅在内存中处理后立即丢弃。

## 🛠️ 技术栈

- 后端：FastAPI（Python 3.13）+ pdfplumber
- 前端：原生 HTML/CSS/JS 单页（由后端同源挂载，无需单独构建）
- 部署：Docker（Render 免费实例可跑）

## 📁 目录结构

```
.
├── backend/
│   ├── main.py              # FastAPI 入口：上传解析、CSV 导出、静态挂载
│   ├── parse_schedule.py    # 课表 PDF 解析（也可命令行单独使用）
│   └── merge_schedule.py    # 多人课表合并、空闲时段统计
├── frontend/
│   └── index.html           # 前端单页
├── Dockerfile               # Render / 任意容器平台部署镜像
├── render.yaml              # Render Blueprint 一键部署配置
├── start.sh                 # 容器启动脚本（读取 PORT）
└── requirements.txt         # Python 依赖
```

## 💻 本地运行

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate

pip install -r requirements.txt
cd backend
python main.py
```

打开 http://127.0.0.1:8000 即可使用（`/api/docs` 查看接口文档）。

也可以直接用 uvicorn 启动，效果相同：

```bash
uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

## 🚀 部署到 Render（免费实例）

### 方式一：Blueprint 一键部署（推荐）

1. 把本仓库推送到 GitHub（仓库根目录需包含 `render.yaml` 与 `Dockerfile`）。
2. 登录 [Render Dashboard](https://dashboard.render.com) → **New** → **Blueprint**。
3. 选择本仓库，Render 会自动读取 `render.yaml`，创建一个名为 `class-course-time` 的
   Docker Web 服务（`plan: free`，健康检查 `/healthz`）。
4. 点击 **Apply**，等待首次构建完成，访问页面给出的 `https://<服务名>.onrender.com` 即可。

### 方式二：手动创建 Web Service

1. Render Dashboard → **New** → **Web Service**，连接本仓库。
2. 关键配置：

   | 配置项 | 值 |
   | --- | --- |
   | Language / Runtime | `Docker` |
   | Dockerfile Path | `./Dockerfile` |
   | Instance Type | `Free` |
   | Health Check Path | `/healthz` |

3. 若改用 **Python** 原生运行时（不使用 Docker），则填：

   | 配置项 | 值 |
   | --- | --- |
   | Build Command | `pip install -r requirements.txt` |
   | Start Command | `uvicorn main:app --app-dir backend --host 0.0.0.0 --port $PORT` |
   | Environment Variable | `PYTHON_VERSION` = `3.13.5` |

   说明：`--app-dir backend` 让 `main.py` 里的 `from parse_schedule import ...` 能正确导入；
   `$PORT` 由 Render 注入，不要写死端口。

### 环境变量（都可不填，用默认值）

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `PORT` | `8000`（Render 注入 `10000`） | 监听端口 |
| `HOST` | `0.0.0.0` | 监听地址 |
| `WEB_CONCURRENCY` | `1` | uvicorn 进程数，免费实例保持 1 |
| `MAX_UPLOAD_BYTES` | `41943040`（40MB） | 单次上传总大小上限，防止内存溢出 |
| `MAX_UPLOAD_FILES` | `80` | 单次上传文件数上限 |

## ⚠️ Render 免费实例注意事项

- **冷启动**：免费实例 15 分钟无请求会休眠，下次访问需 30~60 秒唤醒。
  页面上传时会提示等待，属于正常现象，不要重复点击。
- **内存 512MB / 0.1 CPU**：解析大 PDF 较慢。已内置上传大小与文件数上限（见上表），
  超过会返回 413 并给出中文提示，而不是让实例崩溃。
- **文件不落盘**：上传的 PDF 只在内存中解析，导出后即释放，不做持久化。
- **无持久磁盘**：本项目不使用数据库和磁盘存储，重新部署不会丢数据。

## 🔌 接口说明

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/upload` | 表单字段 `pdf_files`（可多个），返回 UTF-8 BOM 的 CSV；响应头 `X-Student-Count` / `X-Failed-Count` 给出成功与失败人数 |
| `GET` | `/healthz` | 健康检查，云平台探活用 |
| `GET` | `/api/config` | 返回上传上限等运行配置 |
| `GET` | `/api/docs` | Swagger 接口文档 |
| `GET` | `/` | 前端页面 |

错误响应统一为 `{"detail": "中文错误说明"}`，前端会直接把该说明展示给用户。
单个 PDF 解析失败不会导致整批失败，会被跳过并计入 `X-Failed-Count`。

## 🧪 离线自检

仓库内 `.offline_check/` 提供不依赖网络的校验脚本，用于验证解析、统计、
CSV 格式与前端渲染逻辑是否一致：

```bash
python .offline_check/run_check.py                 # 后端逻辑（42 项）
node .offline_check/frontend_check.mjs             # 前端解析与渲染（27 项）
python .offline_check/run_check.py && node .offline_check/e2e_check.mjs  # 前后端联调（8 项）
```

## 📄 许可证

见 [LICENSE](LICENSE)。
