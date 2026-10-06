# /// script
# requires-python = ">=3.10"
# dependencies = ["xlrd"]
# ///
"""
把 114-1 在學人數統計表 (.xls) 轉成整齊的 CSV。

用法：uv run work/etl_enrollment.py
輸出：work/enrollment_114-1.csv（UTF-8 with BOM）
欄位：college, dept_raw, program_raw, gender, count
"""
import csv
import re
from collections import defaultdict
from pathlib import Path

import xlrd

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "東華大學統計資料" / "在學人數統計表"
OUT = ROOT / "work" / "enrollment_114-1.csv"

COL_PROGRAM, COL_COLLEGE, COL_DEPT, COL_GROUP = 0, 1, 2, 3
COL_TOTAL, COL_F, COL_M = 4, 5, 6  # 「總計」底下的 合計、女、男

# 「XX 合計N」小計列決定其下資料屬於哪個學制
SECTION = {"博士班": "博士班", "碩士班": "碩士班", "碩專班": "碩士在職專班", "學士班": "學士班"}


def text(sheet, r, c):
    v = sheet.cell_value(r, c)
    return re.sub(r"\s+", " ", str(v)).strip() if v != "" else ""


def num(v):
    return 0 if v == "" else int(round(float(v)))


def fill_column(sheet, col, rows):
    """
    處理合併儲存格：名稱照理只寫在合併範圍的第一格，但這份檔案有例外，
    所以用「合併範圍內任一格的非空值」當整個範圍的值。
    不在任何合併範圍內的空白格，視為屬於下一個區塊（報表上有一列漏了合併）。
    """
    ranges = [(r0, r1) for r0, r1, c0, c1 in sheet.merged_cells if c0 <= col < c1]
    out = {}
    for r in rows:
        v = text(sheet, r, col)
        if not v:
            for r0, r1 in ranges:
                if r0 <= r < r1:
                    v = next((text(sheet, i, col) for i in range(r0, r1) if text(sheet, i, col)), "")
                    break
        out[r] = v
    # 仍空白的格：往下找到第一個有值的列
    for r in sorted(rows, reverse=True):
        if not out[r] and r + 1 in out:
            out[r] = out[r + 1]
    return out


def main():
    src = next(SRC_DIR.glob("114-1*.xls"))
    sheet = xlrd.open_workbook(src, formatting_info=True).sheet_by_index(0)

    program, data_rows = None, {}
    for r in range(sheet.nrows):
        head = text(sheet, r, COL_PROGRAM)
        if head.startswith("備註"):
            break
        if "總計" in head:
            continue
        if "合計" in head:
            program = SECTION[head.split()[0]]
            continue
        if program and text(sheet, r, COL_GROUP) and isinstance(sheet.cell_value(r, COL_TOTAL), float):
            data_rows[r] = program

    rows = list(data_rows)
    colleges = fill_column(sheet, COL_COLLEGE, rows)
    depts = fill_column(sheet, COL_DEPT, rows)

    totals = defaultdict(int)  # 同一系所、同一學制下的分組加總
    for r, program in data_rows.items():
        college = re.sub(r"[（(].*?[)）]", "", colleges[r]).strip()
        f, m = num(sheet.cell_value(r, COL_F)), num(sheet.cell_value(r, COL_M))
        assert f + m == num(sheet.cell_value(r, COL_TOTAL)), f"第 {r + 1} 列 女+男 不等於合計"
        totals[(college, depts[r], program, "女")] += f
        totals[(college, depts[r], program, "男")] += m

    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["college", "dept_raw", "program_raw", "gender", "count"])
        for key, count in totals.items():
            w.writerow([*key, count])
    print(f"{src.name} → {OUT.relative_to(ROOT)}：{len(totals)} 列，總人數 {sum(totals.values())}")


if __name__ == "__main__":
    main()
