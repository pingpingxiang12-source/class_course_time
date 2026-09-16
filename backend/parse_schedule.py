"""
课表 PDF 解析工具
将教务系统导出的课表 PDF 转换为结构化数据（JSON / CSV）

用法：
    # 解析单个文件，输出为 JSON（默认）
    python3 parse_schedule.py 张三课表.pdf

    # 指定输出格式为 CSV
    python3 parse_schedule.py 张三课表.pdf --format csv

    # 批量解析整个文件夹里的所有 PDF
    python3 parse_schedule.py ./班级课表文件夹/ --batch

    # 指定输出目录
    python3 parse_schedule.py 张三课表.pdf -o ./output/
"""

import pdfplumber
import re
import json
import csv
import argparse
import os
import sys

def parse_schedule_from_bytes(pdf_bytes):
    """从pdf二进制字节解析课表，不读取磁盘文件"""
    from io import BytesIO
    pdf_stream = BytesIO(pdf_bytes)
    return parse_schedule(pdf_stream)

def parse_schedule(pdf_path):
    """解析单个课表 PDF，返回课程列表（每项含星期/节次/课程/周次/教室/教师）"""
    weekday_names = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']
    all_rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for t in page.extract_tables():
                all_rows.extend(t)

    detail_pattern = re.compile(
        r'^(?P<name>[^\(]*?)\*?\((?P<p1>\d+)-(?P<p2>\d+)节\)(?P<weeks>[^/]+)/'
        r'.*?场地[:：](?P<loc>[^/]+)/教师[:：](?P<teacher>[^/]+)/'
    )

    last_name_by_col = {}
    courses = []

    for row in all_rows:
        if len(row) < 9:
            continue
        for col_idx in range(2, 9):
            cell = row[col_idx]
            if not cell or not isinstance(cell, str):
                continue
            clean = cell.replace('\n', '').strip()
            if not clean:
                continue

            if '节)' not in clean:
                last_name_by_col[col_idx] = clean.rstrip('*').strip()
                continue

            m = detail_pattern.search(clean)
            if not m:
                continue

            name = m.group('name').strip()
            if not name:
                name = last_name_by_col.get(col_idx, '未知课程')

            courses.append({
                '星期': weekday_names[col_idx - 2],
                '节次': f"{m.group('p1')}-{m.group('p2')}",
                '课程': name,
                '周次': m.group('weeks').strip(),
                '教室': m.group('loc').strip(),
                '教师': m.group('teacher').strip(),
            })

    seen = set()
    unique_courses = []
    for c in courses:
        key = (c['星期'], c['节次'], c['课程'])
        if key not in seen:
            seen.add(key)
            unique_courses.append(c)

    return unique_courses


def save_as_json(courses, out_path):
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(courses, f, ensure_ascii=False, indent=2)


def save_as_csv(courses, out_path):
    if not courses:
        return
    with open(out_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=courses[0].keys())
        writer.writeheader()
        writer.writerows(courses)


def process_one(pdf_path, out_dir, fmt):
    name = os.path.splitext(os.path.basename(pdf_path))[0]
    courses = parse_schedule(pdf_path)

    if not courses:
        print(f"⚠️  {pdf_path} 未能提取到任何课程，可能是表格结构不同，需要调整解析规则")
        return None

    out_path = os.path.join(out_dir, f"{name}.{fmt}")
    if fmt == 'json':
        save_as_json(courses, out_path)
    else:
        save_as_csv(courses, out_path)

    print(f"✅ {pdf_path} -> {out_path}（共 {len(courses)} 门课）")
    return out_path


def main():
    parser = argparse.ArgumentParser(description='课表 PDF 解析工具')
    parser.add_argument('path', help='PDF 文件路径，或 --batch 模式下的文件夹路径')
    parser.add_argument('--format', choices=['json', 'csv'], default='json', help='输出格式，默认 json')
    parser.add_argument('-o', '--output', default='.', help='输出目录，默认当前目录')
    parser.add_argument('--batch', action='store_true', help='批量处理文件夹内所有 PDF')
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    if args.batch:
        if not os.path.isdir(args.path):
            print(f"错误：{args.path} 不是一个文件夹")
            sys.exit(1)
        pdf_files = [f for f in os.listdir(args.path) if f.lower().endswith('.pdf')]
        if not pdf_files:
            print("该文件夹下没有找到 PDF 文件")
            sys.exit(1)
        print(f"发现 {len(pdf_files)} 个 PDF 文件，开始批量解析...\n")
        for f in pdf_files:
            process_one(os.path.join(args.path, f), args.output, args.format)
    else:
        if not os.path.isfile(args.path):
            print(f"错误：找不到文件 {args.path}")
            sys.exit(1)
        process_one(args.path, args.output, args.format)


if __name__ == '__main__':
    main()