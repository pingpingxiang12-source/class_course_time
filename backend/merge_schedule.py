"""
多人课表合并 - 找共同空闲时间
输入：多个已解析好的课表 JSON 文件（parse_schedule.py 的输出）
输出：一张"星期 x 节次"的占用人数统计表，以及推荐的共同空闲时段

用法：
    python3 merge_schedules.py ./解析结果/ -o 共同空闲时间.csv
"""

import json
import os
import argparse
import csv
from collections import defaultdict

WEEKDAYS = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']
# 常见节次分组：按你们学校实际的"节次"划分调整这里即可
PERIODS = ['1-2', '3-4', '5-6', '7-8', '9-10', '11-12']


def load_all_students(json_dir):
    """读取文件夹下所有 JSON 文件，返回 {学生名: 课程列表}"""
    students = {}
    for fname in os.listdir(json_dir):
        if not fname.lower().endswith('.json'):
            continue
        name = os.path.splitext(fname)[0]
        with open(os.path.join(json_dir, fname), encoding='utf-8') as f:
            students[name] = json.load(f)
    return students


def week_in_range(week_num, weeks_str):
    """判断某一周（如第3周）是否落在这门课的周次范围内
    weeks_str 形如 '1-5周,7-11周' 或 '5-7周(单),8-19周'
    """
    weeks_str = weeks_str.replace('周', '')
    for part in weeks_str.split(','):
        part = part.strip()
        odd_only = '(单)' in part
        even_only = '(双)' in part
        part = part.replace('(单)', '').replace('(双)', '')
        if '-' not in part:
            continue
        try:
            start, end = map(int, part.split('-'))
        except ValueError:
            continue
        if start <= week_num <= end:
            if odd_only and week_num % 2 == 0:
                continue
            if even_only and week_num % 2 == 1:
                continue
            return True
    return False


def build_busy_matrix(students, week_num=None):
    """构建 {(星期, 节次): [占用的学生名单]} 的字典
    week_num 不为空时，只统计当周有效的课
    注意：用 set 去重，避免同一个人因为该时段有多条课程记录
    （真实排课冲突，或解析产生的重复条目）被重复计数
    """
    busy = defaultdict(set)
    for name, courses in students.items():
        for c in courses:
            if week_num is not None:
                if not week_in_range(week_num, c['周次']):
                    continue
            busy[(c['星期'], c['节次'])].add(name)
    return {k: sorted(v) for k, v in busy.items()}


def print_report(students, busy, week_num=None):
    total = len(students)
    title = f"（第 {week_num} 周）" if week_num else "（未指定具体周次，统计全学期所有课程）"
    print(f"\n全班共 {total} 人 {title}\n")
    print(f"{'时间段':<12}{'有课人数':<10}空闲人数  空闲名单")
    print('-' * 70)

    rows = []
    for day in WEEKDAYS:
        for period in PERIODS:
            occupied = busy.get((day, period), [])
            free_count = total - len(occupied)
            free_names = [s for s in students if s not in occupied]
            rows.append({
                '星期': day, '节次': period,
                '有课人数': len(occupied), '空闲人数': free_count,
                '空闲名单': ','.join(free_names)
            })
            mark = '⭐' if free_count == total else ''
            print(f"{day} {period:<8}{len(occupied):<10}{free_count:<10}{mark}")

    # 推荐：全班都空闲的时间段
    best = [r for r in rows if r['空闲人数'] == total]
    print('\n=== 全班都没课的时间段（最适合开班会）===')
    if best:
        for r in best:
            print(f"  {r['星期']} 第{r['节次']}节")
    else:
        print("  没有全班都空闲的时间段，建议看下面接近满员空闲的时段：")
        rows_sorted = sorted(rows, key=lambda r: -r['空闲人数'])
        for r in rows_sorted[:5]:
            print(f"  {r['星期']} 第{r['节次']}节  空闲 {r['空闲人数']}/{total} 人")

    return rows


def save_csv(rows, out_path):
    with open(out_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['星期', '节次', '有课人数', '空闲人数', '空闲名单'])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n已保存完整表格到 {out_path}")


def main():
    parser = argparse.ArgumentParser(description='多人课表合并 - 找共同空闲时间')
    parser.add_argument('json_dir', help='存放各个学生 JSON 文件的文件夹')
    parser.add_argument('-w', '--week', type=int, default=None, help='指定第几周（不填则统计全学期）')
    parser.add_argument('-o', '--output', default='共同空闲时间.csv', help='输出 CSV 文件路径')
    args = parser.parse_args()

    students = load_all_students(args.json_dir)
    if not students:
        print(f"错误：{args.json_dir} 下没有找到任何 JSON 文件，请先用 parse_schedule.py 批量解析")
        return

    busy = build_busy_matrix(students, args.week)
    rows = print_report(students, busy, args.week)
    save_csv(rows, args.output)


if __name__ == '__main__':
    main()