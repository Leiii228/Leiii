# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
把 data/ 的三個 CSV 整理成網頁可直接載入的 docs/data.js。

用法：uv run work/build_data.py
網頁用法：<script src="data.js"></script> 之後讀 window.BI_DATA
（用 <script> 載入而不是 fetch，雙擊 index.html 用 file:// 開也能讀到）

為了讓檔案小：
- 丟掉網頁用不到的欄位（dept_raw、program_raw、identity 等），再加總
- 學期、系所、學位別、性別、休學原因都存成「代碼表 + 索引」，每列只放數字
- 學院由系所決定（系所對照表一對一），存在 depts 裡，不在每列重複
"""
import csv
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "docs" / "data.js"

DEGREES = ["學士", "碩士", "博士"]
GENDERS = ["女", "男"]


def read(name):
    with (DATA / name).open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def sem_key(s):
    y, t = s.split("-")
    return int(y), int(t)


def main():
    mapping = read("dept_mapping.csv")
    enrollment = read("enrollment.csv")
    leave = read("leave.csv")

    # 代碼表
    dept_college = {m["dept"]: m["college"] for m in mapping}
    colleges = sorted({m["college"] for m in mapping})
    depts = sorted(dept_college, key=lambda d: (colleges.index(dept_college[d]), d))
    semesters = sorted({r["semester"] for r in enrollment + leave}, key=sem_key)
    reason_group = {}
    for r in leave:
        reason_group.setdefault(r["reason"], r["reason_group"])
    reasons = sorted(reason_group, key=lambda x: (reason_group[x] != "自請休學", x))

    idx = lambda seq: {v: i for i, v in enumerate(seq)}
    i_sem, i_dept, i_deg, i_gen, i_rea = map(idx, (semesters, depts, DEGREES, GENDERS, reasons))

    # 資料裡的學院要和對照表一致，才能只靠系所推回學院
    for r in enrollment + leave:
        assert dept_college[r["dept"]] == r["college"], f"學院不一致：{r}"

    enr = defaultdict(int)
    for r in enrollment:
        enr[(i_sem[r["semester"]], i_dept[r["dept"]], i_deg[r["degree"]], i_gen[r["gender"]])] += int(r["count"])

    lv = defaultdict(lambda: [0, 0])
    for r in leave:
        k = (i_sem[r["semester"]], i_dept[r["dept"]], i_deg[r["degree"]], i_gen[r["gender"]], i_rea[r["reason"]])
        lv[k][0] += int(r["new_leave"])
        lv[k][1] += int(r["on_leave_end"])

    payload = {
        "generated": date.today().isoformat(),
        "semesters": semesters,
        "colleges": colleges,
        "depts": [
            {"name": d, "college": colleges.index(dept_college[d]),
             "aliases": [a.strip() for a in m["aliases"].split(";") if a.strip()]}
            for d in depts for m in mapping if m["dept"] == d
        ],
        "degrees": DEGREES,
        "genders": GENDERS,
        "reasons": [{"name": x, "group": reason_group[x]} for x in reasons],
        "enrollment": {
            "fields": ["semester", "dept", "degree", "gender", "count"],
            "rows": [[*k, v] for k, v in sorted(enr.items())],
        },
        "leave": {
            "fields": ["semester", "dept", "degree", "gender", "reason", "new_leave", "on_leave_end"],
            "rows": [[*k, *v] for k, v in sorted(lv.items()) if any(v)],
        },
    }

    OUT.parent.mkdir(exist_ok=True)
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # 每列資料換行，方便人看 diff；欄位定義見 fields，代碼對照見上方各清單
    body = body.replace("],[", "],\n[")
    OUT.write_text(
        "// 由 work/build_data.py 從 data/*.csv 產生，請勿手動修改\n"
        f"window.BI_DATA = {body};\n",
        encoding="utf-8",
    )

    # 核對
    sem = i_sem["114-1"]
    total_114_1 = sum(v for k, v in enr.items() if k[0] == sem)
    print(f"→ {OUT.relative_to(ROOT)}：{OUT.stat().st_size / 1024:.1f} KB")
    print(f"  學期 {len(semesters)}、學院 {len(colleges)}、系所 {len(depts)}、休學原因 {len(reasons)}")
    print(f"  在學 {len(payload['enrollment']['rows'])} 列、休學 {len(payload['leave']['rows'])} 列")
    print(f"  總數核對：在學 {sum(enr.values())} / 原檔 {sum(int(r['count']) for r in enrollment)}；"
          f"學期間休學 {sum(v[0] for v in lv.values())} / 原檔 {sum(int(r['new_leave']) for r in leave)}；"
          f"學期底休學 {sum(v[1] for v in lv.values())} / 原檔 {sum(int(r['on_leave_end']) for r in leave)}")
    print(f"  114-1 在學人數合計：{total_114_1} {'✅' if total_114_1 == 10035 else '❌ 應為 10035'}")


if __name__ == "__main__":
    main()
