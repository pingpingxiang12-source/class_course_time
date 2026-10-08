"""班级课表统计网站 —— FastAPI 后端

支持本地运行，也支持部署到 Render 等云平台：
- 监听端口优先读取环境变量 PORT（Render 会注入），默认 8000
- 监听地址默认 0.0.0.0，容器/云平台可以从外部访问
- 提供 /healthz 健康检查端点，方便云平台探活

启动方式（二选一）：
    python main.py
    uvicorn main:app --host 0.0.0.0 --port $PORT
"""

import csv
import os
import urllib.parse
from io import BytesIO, StringIO

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from merge_schedule import build_busy_matrix, print_report, week_in_range  # noqa: F401
from parse_schedule import parse_schedule_from_bytes

# 单次请求允许上传的最大总字节数（免费实例内存有限，避免 OOM）
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", 40 * 1024 * 1024))
# 单次请求允许上传的最大文件数
MAX_UPLOAD_FILES = int(os.environ.get("MAX_UPLOAD_FILES", 80))

# main.py 所在目录（backend/），frontend 在它的同级目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.normpath(os.path.join(BASE_DIR, os.pardir, "frontend"))

CSV_FIELDNAMES = ["周次", "星期", "节次", "有课人数", "空闲人数", "空闲名单"]

# 教务系统导出的文件名常见形如「张三课表.pdf」「张三-课程表.pdf」，
# 去掉这些后缀后剩下的才是学生姓名，否则空闲名单里会出现「张三课表」这种脏数据。
# 必须按长度从长到短匹配，否则「的课表」会先被「课表」截断，留下「王五的」。
NAME_SUFFIXES = tuple(sorted({
    "课表", "课程表", "的课表", "的课程表", "学生课表", "个人课表",
    "-课表", "_课表", "课表)", "课表）", "课表】", "课表]",
}, key=len, reverse=True))

app = FastAPI(title="班级课表统计工具", docs_url="/api/docs", openapi_url="/api/openapi.json")

# 同源部署（前端由本服务挂载）本不需要 CORS；
# 这里保留宽松策略，方便前端单独部署到 Vercel 等平台时跨域调用 /api/upload。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def student_name_from_filename(filename):
    """从上传文件名推断学生姓名：去掉扩展名与「课表 / 课程表」等常见后缀。"""
    base = os.path.basename(filename or "")
    if base.lower().endswith(".pdf"):
        base = base[:-4]
    name = base.strip()
    # 后缀可能叠加（例如「张三课表.pdf.x」被重命名过），循环剥两轮足够
    for _ in range(2):
        for suffix in NAME_SUFFIXES:
            if name.endswith(suffix) and len(name) > len(suffix):
                name = name[: -len(suffix)].strip(" -_()（）")
                break
        else:
            break
    return name.strip()


def max_week_of_semester(students):
    """从所有课程里提取整个学期最大的周数"""
    max_w = 1
    for courses in students.values():
        for c in courses:
            weeks = c["周次"].replace("周", "").replace("(单)", "").replace("(双)", "")
            for part in weeks.split(","):
                part = part.strip()
                if "-" in part:
                    try:
                        start, end = map(int, part.split("-"))
                        max_w = max(max_w, end)
                    except ValueError:
                        continue
    return max_w


@app.get("/healthz")
async def healthz():
    """健康检查端点：云平台用它判断实例是否可用。"""
    return {"status": "ok", "service": "class-course-time", "frontend": os.path.isdir(FRONTEND_DIR)}


@app.post("/api/upload")
async def upload_pdfs(pdf_files: list[UploadFile] = File(...)):
    if not pdf_files:
        raise HTTPException(status_code=400, detail="没有收到任何 PDF 文件")
    if len(pdf_files) > MAX_UPLOAD_FILES:
        raise HTTPException(status_code=413, detail=f"一次最多上传 {MAX_UPLOAD_FILES} 个 PDF 文件")

    students = {}
    total_bytes = 0
    failed = []

    for upload_file in pdf_files:
        pdf_bytes = await upload_file.read()
        total_bytes += len(pdf_bytes)
        if total_bytes > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"上传文件过大，一次最多 {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
            )

        student_name = student_name_from_filename(upload_file.filename)
        if not student_name:
            student_name = f"未知学生{len(students) + 1}"
        # 同名文件（如两个人文件重名）加序号后缀，避免互相覆盖
        if student_name in students:
            index = 2
            while f"{student_name}({index})" in students:
                index += 1
            student_name = f"{student_name}({index})"

        try:
            courses = parse_schedule_from_bytes(pdf_bytes)
        except Exception as exc:  # PDF 损坏 / 加密 / 非课表格式
            failed.append(f"{student_name}（{type(exc).__name__}）")
            continue

        if not courses:
            failed.append(f"{student_name}（未解析到课程）")
            continue

        students[student_name] = courses

    if not students:
        detail = "未能解析到任何课表数据，请确认上传的是教务系统导出的课表 PDF"
        if failed:
            detail += "；解析失败：" + "、".join(failed)
        raise HTTPException(status_code=400, detail=detail)

    total_weeks = max_week_of_semester(students)

    rows = []
    for week in range(1, total_weeks + 1):
        busy = build_busy_matrix(students, week_num=week)
        week_rows = print_report(students, busy, week_num=week)
        for r in week_rows:
            r["周次"] = week
        rows.extend(week_rows)

    text_io = StringIO()
    writer = csv.writer(text_io)
    writer.writerow(CSV_FIELDNAMES)
    # 用底层 csv.writer 而不是 DictWriter.writerows：
    # 姓名等字段一旦含逗号/引号/换行，writer 会自动加引号并按标准转义，
    # 前端的 parseCsvLine 能正确还原，也不会破坏列数。
    for row in rows:
        writer.writerow([row[f] for f in CSV_FIELDNAMES])

    output_buffer = BytesIO(text_io.getvalue().encode("utf-8-sig"))
    output_buffer.seek(0)

    filename = "班级课表逐周统计结果.csv"
    encoded_filename = urllib.parse.quote(filename, encoding="utf-8")
    headers = {
        "Content-Disposition": f"attachment; filename=\"result.csv\"; filename*=utf-8''{encoded_filename}",
        # 让前端在解析失败时也能读到统计信息
        "X-Student-Count": str(len(students)),
        "X-Failed-Count": str(len(failed)),
    }

    return StreamingResponse(output_buffer, media_type="text/csv; charset=utf-8", headers=headers)


@app.get("/api/config")
async def runtime_config():
    """前端可用来确认服务端限制与运行状态。"""
    return {
        "maxUploadMb": MAX_UPLOAD_BYTES // (1024 * 1024),
        "maxUploadFiles": MAX_UPLOAD_FILES,
        "frontendMounted": os.path.isdir(FRONTEND_DIR),
    }


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):  # pragma: no cover - 兜底路径
    return JSONResponse(status_code=500, content={"detail": f"服务器内部错误：{exc}"})


# 静态前端：必须放在所有 API 路由之后注册，
# 否则挂在 "/" 上的 StaticFiles 会拦截 /api/* 请求。
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")
else:  # 本地缺少 frontend 目录时给出明确提示，而不是启动即崩溃
    @app.get("/")
    async def missing_frontend():
        return JSONResponse(
            status_code=500,
            content={"detail": f"未找到前端目录：{FRONTEND_DIR}"},
        )


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)
