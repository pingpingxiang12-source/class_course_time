from fastapi import FastAPI, UploadFile, File
from fastapi.responses import StreamingResponse
import urllib.parse
from io import BytesIO, StringIO
import csv
from parse_schedule import parse_schedule_from_bytes
from merge_schedule import build_busy_matrix, print_report, week_in_range

app = FastAPI()

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def max_week_of_semester(students):
    """从所有课程里提取整个学期最大的周数"""
    max_w = 1
    for courses in students.values():
        for c in courses:
            weeks = c['周次'].replace('周', '').replace('(单)', '').replace('(双)', '')
            for part in weeks.split(','):
                part = part.strip()
                if '-' in part:
                    try:
                        start, end = map(int, part.split('-'))
                        max_w = max(max_w, end)
                    except ValueError:
                        continue
    return max_w


@app.post("/upload")
async def upload_pdfs(pdf_files: list[UploadFile] = File(...)):
    students = {}
    for upload_file in pdf_files:
        pdf_bytes = await upload_file.read()
        courses = parse_schedule_from_bytes(pdf_bytes)
        student_name = upload_file.filename.rsplit(".pdf", 1)[0]
        students[student_name] = courses

    if not students:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="未能解析到任何课表数据，请检查PDF文件")

    total_weeks = max_week_of_semester(students)

    rows = []
    for week in range(1, total_weeks + 1):
        busy = build_busy_matrix(students, week_num=week)
        week_rows = print_report(students, busy, week_num=week)
        for r in week_rows:
            r['周次'] = week
        rows.extend(week_rows)

    output_buffer = BytesIO()
    text_io = StringIO()
    fieldnames = ['周次', '星期', '节次', '有课人数', '空闲人数', '空闲名单']
    writer = csv.DictWriter(text_io, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

    output_buffer.write(text_io.getvalue().encode("utf-8-sig"))
    output_buffer.seek(0)

    filename = "班级课表逐周统计结果.csv"
    encoded_filename = urllib.parse.quote(filename, encoding='utf-8')
    headers = {
        "Content-Disposition": f"attachment; filename=\"result.csv\"; filename*=utf-8''{encoded_filename}"
    }

    return StreamingResponse(output_buffer, media_type="text/csv", headers=headers)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
