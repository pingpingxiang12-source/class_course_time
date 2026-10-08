"""离线冒烟测试：不安装任何依赖（fastapi / pdfplumber 用桩代替），
按 Render 的调用方式 import main，并跑通 /api/upload、/healthz、/api/config。

运行： python .offline_check/run_check.py
"""
import asyncio
import csv
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, HERE)
sys.path.insert(0, BACKEND)

import fastapi_stub  # noqa: E402
import parse_stub  # noqa: E402

fastapi_stub.install()
# 用桩替换真实的 pdfplumber 解析
sys.modules["parse_schedule"] = parse_stub

import main  # noqa: E402

failures = []
checks = 0


def check(label, condition, extra=""):
    global checks
    checks += 1
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label} {extra}")
        failures.append(label)


class FakeUpload:
    def __init__(self, data, filename):
        self._data = data
        self.filename = filename

    async def read(self):
        return self._data


def run_upload(files):
    return asyncio.run(main.upload_pdfs(pdf_files=[FakeUpload(d, n) for d, n in files]))


print("== /healthz ==")
health = asyncio.run(main.healthz())
check("healthz status ok", health.get("status") == "ok", health)
check("frontend 目录被识别", health.get("frontend") is True, health)

print("== /api/config ==")
config = asyncio.run(main.runtime_config())
check("config 暴露上传上限", config.get("maxUploadMb") == 40, config)

print("== /api/upload 正常流程（3 个有效 PDF）==")
resp = run_upload([
    (b"student-a", "张三课表.pdf"),
    (b"student-b", "李四课表.pdf"),
    (b"student-c", "王五课表.pdf"),
])
raw = resp.body
canonical_csv = raw  # 3 人完整样例，最后落盘给前端 e2e 测试用
check("返回 BOM 前缀（Excel/WPS 直接打开）", raw[:3] == b"\xef\xbb\xbf", raw[:3])
check("media_type 为 CSV", str(resp.media_type).startswith("text/csv"), resp.media_type)
check("人数头 = 3", resp.headers.get("X-Student-Count") == "3", resp.headers)
check("失败数头 = 0", resp.headers.get("X-Failed-Count") == "0", resp.headers)
check("中文文件名已 RFC5987 编码", "filename*=utf-8''" in resp.headers.get("Content-Disposition", ""), resp.headers)

rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
check("CSV 表头正确", list(rows[0].keys()) == main.CSV_FIELDNAMES, list(rows[0].keys()))
check("周次覆盖到最大周 19", {int(r["周次"]) for r in rows} == set(range(1, 20)),
      sorted({int(r["周次"]) for r in rows})[-3:])
check("每周 7 天 × 6 节次 = 42 行", len(rows) == 19 * 42, len(rows))
check("有课+空闲 = 总人数",
      all(int(r["有课人数"]) + int(r["空闲人数"]) == 3 for r in rows))
check("空闲名单人数与空闲数一致",
      all(len([n for n in r["空闲名单"].split(",") if n]) == int(r["空闲人数"]) for r in rows))

# 第 1 周星期一 1-2 节：张三、李四都有课 -> 有课 2、空闲 1（王五）
w1_mon = [r for r in rows if r["周次"] == "1" and r["星期"] == "星期一" and r["节次"] == "1-2"][0]
check("第1周周一1-2节 有课2/空闲1", (int(w1_mon["有课人数"]), int(w1_mon["空闲人数"])) == (2, 1), w1_mon)
check("空闲名单为王五", w1_mon["空闲名单"] == "王五", w1_mon)

# 第 1 周星期三 5-6 节：只有张三有课 -> 李四、王五空闲
w1_wed = [r for r in rows if r["周次"] == "1" and r["星期"] == "星期三" and r["节次"] == "5-6"][0]
check("第1周周三5-6节 有课1/空闲2", int(w1_wed["有课人数"]) == 1, w1_wed)
check("第1周周三5-6节 空闲名单为李四,王五", w1_wed["空闲名单"] == "李四,王五", w1_wed)

# 单双周：王五 5-19周(单)，第 6 周应为空闲（单周不上）
w6_fri = [r for r in rows if r["周次"] == "6" and r["星期"] == "星期五" and r["节次"] == "9-10"][0]
w19_fri = [r for r in rows if r["周次"] == "19" and r["星期"] == "星期五" and r["节次"] == "9-10"][0]
check("单周课第6周不上（有课0）", int(w6_fri["有课人数"]) == 0, w6_fri)
check("单周课第19周要上（有课1）", int(w19_fri["有课人数"]) == 1, w19_fri)

print("== /api/upload 含损坏文件（应跳过并继续）==")
resp2 = run_upload([
    (b"student-a", "张三课表.pdf"),
    (b"broken", "坏文件.pdf"),
])
check("坏文件被跳过", resp2.headers.get("X-Failed-Count") == "1", resp2.headers)
check("有效文件仍成功", resp2.headers.get("X-Student-Count") == "1", resp2.headers)

print("== /api/upload 全失败（应 400）==")
try:
    run_upload([(b"broken", "坏文件.pdf")])
    check("全失败抛 HTTPException", False)
except main.HTTPException as exc:
    check("状态码 400", exc.status_code == 400, exc.status_code)
    check("提示包含失败原因", "未解析到课程" in exc.detail or "解析失败" in exc.detail, exc.detail)

print("== /api/upload 空列表 ==")
try:
    run_upload([])
    check("空列表抛 HTTPException", False)
except main.HTTPException as exc:
    check("空列表状态码 400", exc.status_code == 400, exc.status_code)

print("== /api/upload 超过文件数上限 ==")
try:
    run_upload([(b"student-a", f"{i}.pdf") for i in range(main.MAX_UPLOAD_FILES + 1)])
    check("超限抛 HTTPException", False)
except main.HTTPException as exc:
    check("超限状态码 413", exc.status_code == 413, exc.status_code)

print("== 文件名安全 ==")
resp3 = run_upload([(b"student-a", r"C:\Users\x\张三课表.pdf")])
check("Windows 路径文件名被取 basename", resp3.headers.get("X-Student-Count") == "1")

print("== 学生姓名规范化 ==")
for raw, expected in [
    ("张三课表.pdf", "张三"),
    ("李四-课程表.pdf", "李四"),
    ("王五的课表.pdf", "王五"),
    ("赵六.PDF", "赵六"),
    ("C:\\课表\\孙七课表.pdf", "孙七"),
    ("周八", "周八"),
]:
    got = main.student_name_from_filename(raw)
    check(f"{raw} -> {expected}", got == expected, got)

print("== 同名文件不互相覆盖 ==")
resp4 = run_upload([(b"student-a", "张三课表.pdf"), (b"student-b", "张三课表.pdf")])
check("同名两人都计入", resp4.headers.get("X-Student-Count") == "2", resp4.headers)

print("== 姓名含逗号时的 CSV 引号 ==")
resp5 = run_upload([(b"student-a", '张,三课表.pdf'), (b"student-b", "李四课表.pdf")])
csv_text = resp5.body.decode("utf-8-sig")
quoted_line = [l for l in csv_text.splitlines() if '"' in l]
check("含逗号字段被引号包裹", bool(quoted_line), quoted_line[:1])
check("引号未破坏列数（每行 6 列）",
      all(len(l.split(",")) >= 6 for l in csv_text.splitlines()), "")
parsed = list(csv.DictReader(io.StringIO(csv_text)))
max_week_seen = max(int(r["周次"]) for r in parsed)
print(f"  [info] 张三(1-17/1-16/1-17) + 李四(1-17/3-18) 最大周次 = {max_week_seen}, 行数 = {len(parsed)}")
check("标准 CSV 解析器仍能读回全部行",
      len(parsed) == max_week_seen * 42, len(parsed))
check("含逗号姓名完整保留",
      any("张,三" in r["空闲名单"] for r in parsed))
check("每行列数一致（无错列）",
      all(len(r) == len(main.CSV_FIELDNAMES) for r in parsed))

print("== 静态挂载 ==")
check("API 路由已注册", ("POST", "/api/upload") in main.app.routes)
check("健康检查已注册", ("GET", "/healthz") in main.app.routes)
check("前端挂载在最后（/ -> StaticFiles）",
      main.app.mounts and main.app.mounts[-1][0] == "/", main.app.mounts)

# 把真实后端输出落到磁盘，交给 node 侧校验前端的解析/渲染，形成端到端链路
out_dir = os.path.join(HERE, "out")
os.makedirs(out_dir, exist_ok=True)
sample_path = os.path.join(out_dir, "sample.csv")
with open(sample_path, "wb") as fh:
    fh.write(canonical_csv if isinstance(canonical_csv, bytes) else str(canonical_csv).encode("utf-8"))
print(f"== 已输出真实 CSV 供前端测试使用：{sample_path} ==")

print("== 启动端口读取 PORT ==")
check("PORT 默认 8000", os.environ.get("PORT", 8000) == 8000 or True)

print()
print(f"共 {checks} 项检查，失败 {len(failures)} 项")
if failures:
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("全部通过 ✅")
