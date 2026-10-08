"""解析桩：按“PDF 内容”映射到预置课程，用于离线跑通 /api/upload 全流程。"""
from merge_schedule import WEEKDAYS

# 每个学生一份课表：(星期, 节次, 课程, 周次)
FIXTURES = {
    b"student-a": [
        ("星期一", "1-2", "高等数学", "1-17周"),
        ("星期二", "3-4", "大学英语", "1-16周"),
        ("星期三", "5-6", "数据结构", "1-17周"),
    ],
    b"student-b": [
        ("星期一", "1-2", "高等数学", "1-17周"),
        ("星期四", "7-8", "体育", "3-18周"),
    ],
    b"student-c": [
        ("星期五", "9-10", "选修课", "5-19周(单)"),
        ("星期四", "7-8", "体育", "3-18周"),
    ],
    b"broken": "RAISE",
}

CALLS = []


def parse_schedule_from_bytes(pdf_bytes):
    CALLS.append(pdf_bytes)
    data = FIXTURES.get(pdf_bytes, [])
    if data == "RAISE":
        raise ValueError("模拟损坏的 PDF")
    return [
        {"星期": d, "节次": p, "课程": name, "周次": weeks, "教室": "A101", "教师": "张老师"}
        for d, p, name, weeks in data
    ]
