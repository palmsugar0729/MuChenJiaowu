"""导出工资结算表（Phase 4）。

★ **本轮唯一的硬性验收标准**：同一批数据，桌面版导一份、服务端导一份，
  逐单元格比对，每个单元格的值 / 公式 / 底色 / 对齐 / 列宽都一样
  （`docs/实施计划.md` 第六节）。

  ⚠️ 是「**单元格**一致」，不是「文件字节一致」—— openpyxl 每次 `save()`
     都往 `docProps/core.xml` 写当前时间戳，同一个工作簿存两次字节都不同。

  比对用的「同一批数据」有两种来源：
    1. 代码现造的合成数据（**CI 里也跑**，不依赖任何本地文件）
    2. `codes/desktop/dist/records.json` 里那份真实生产数据（只在已经装了
       桌面版源码的机器上跑，缺文件就 skip）

  ⚠️ 桌面版源码在 `codes/desktop/` 是**被 git 跟踪的**（只有 `dist/` 被忽略），
     所以第 1 种对拍在 CI 上也能生效 —— 这条测试才算真的守着格式。

⚠️ **费率是两边有意不同的地方**：桌面版 `Record.rate` 查的是 `config.CLASS_RATES`
   静态表（导出时现查），服务端用的是 `lessons.rate`（排课时的快照）。
   `实施计划.md` 已定快照才是对的（改费率不该篡改历史工资表）。
   所以对拍时**服务端这一侧也要按静态表填 rate**，模拟「排课之后没再改过费率」的月份 ——
   拿改过费率的月份比对必然对不上，那不是 bug。
"""

import json
import sys
from datetime import date as Date
from datetime import datetime as DateTime
from datetime import time as Time
from importlib import util as importlib_util
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

import pytest
from openpyxl import load_workbook

from app.exporters import salary_excel
from app.exporters.salary_excel import (
    COLOR_PALETTE,
    COLUMN_WIDTHS,
    HEADERS,
    ExportRow,
    TeacherSheet,
)
from app.models import LessonStatus, Role
from app.routers.attendance import XLSX_MEDIA_TYPE

EXPORT = "/api/attendance/export"

# 与 conftest 里 `make_lesson` 的默认日期（2026-10-05）配套。
# ⚠️ 用默认日期造的课都落在这个月 —— 查错月份拿到的是 400 的 JSON，不是 xlsx。
DEFAULT_MONTH = "2026-10"

_SERVER_DIR = Path(__file__).resolve().parents[1]
DESKTOP_DIR = _SERVER_DIR.parent / "desktop"
RECORDS_JSON = DESKTOP_DIR / "dist" / "records.json"

# 桌面版 `config.CLASS_RATES` 那 5 个班型的费率（对拍时用；不 import，免得耦合）
CLASS_RATES = {"1对1": 80, "1对2": 100, "1对3": 100, "1对4": 110, "1对5": 120}
DEFAULT_RATE = 100


def export(client, headers, month=DEFAULT_MONTH, teacher_id=None):
    url = f"{EXPORT}?month={month}"
    if teacher_id is not None:
        url += f"&teacher_id={teacher_id}"
    return client.get(url, headers=headers)


def load(content: bytes):
    """从字节读回工作簿。

    ⚠️ 用 `BytesIO` 而不是 `data_only=True` —— 我们要看的是**公式字符串**
       （`=D4*E4`），`data_only` 会把公式换成缓存值（而 openpyxl 写出来的文件
       根本没有缓存值，读回来全是 None）。
    """
    return load_workbook(BytesIO(content))


# ── 逐单元格快照 ──────────────────────────────────


def _norm(value):
    """比对前的归一化。

    桌面版的 A 列是 `datetime.datetime`（`storage.py` 解析 JSON 时带的零点），
    服务端写的是 `datetime.date`。渲染出来一模一样，但 `==` 不相等 ——
    不归一化的话这条对拍会因为「日期比日期多了一个 00:00」而假红。
    """
    if isinstance(value, DateTime):
        return value.date()
    return value


def snapshot(content: bytes) -> dict:
    """把工作簿摊成纯数据结构，便于两边直接 `==`。

    只取**属于格式的那些属性**：值、数字格式、底色、字体、对齐、四边框。
    """
    wb = load(content)
    sheets: dict = {}
    for ws in wb.worksheets:
        cells: dict = {}
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column):
            for cell in row:
                filled = cell.fill is not None and cell.fill.fill_type == "solid"
                cells[cell.coordinate] = (
                    _norm(cell.value),
                    cell.number_format,
                    cell.fill.start_color.rgb if filled else None,
                    cell.font.bold,
                    cell.font.size,
                    cell.alignment.horizontal,
                    cell.alignment.vertical,
                    tuple(
                        getattr(cell.border, side).style
                        for side in ("left", "right", "top", "bottom")
                    ),
                )
        sheets[ws.title] = {
            "cells": cells,
            "merged": sorted(str(r) for r in ws.merged_cells.ranges),
            "widths": {k: v.width for k, v in ws.column_dimensions.items()},
        }
    return sheets


def fill_of(content: bytes, coordinate: str) -> str | None:
    return load(content).active[coordinate].fill.start_color.rgb


# ── 桌面版对拍 ────────────────────────────────────


@pytest.fixture(scope="module")
def desktop():
    """把桌面版的三个平铺模块装进 `sys.modules`。

    ⚠️ 桌面版是**平铺模块**（`excel_exporter.py` 里写 `from config import ...`），
       不是包。所以得先把 `config` / `models` 按名字塞进 `sys.modules`，
       再执行 `excel_exporter` —— 否则它的绝对导入会跑去别处找。
       卸载时把这三个名字恢复原状，不污染其它测试。
    """
    if not (DESKTOP_DIR / "excel_exporter.py").exists():
        pytest.skip("桌面版源码不在（服务端单独部署时正常）")

    names = ("config", "models", "excel_exporter")
    saved = {name: sys.modules.get(name) for name in names}
    loaded: dict = {}
    try:
        for name in names:  # ⚠️ 顺序不能乱：excel_exporter 依赖前两个
            spec = importlib_util.spec_from_file_location(
                name, DESKTOP_DIR / f"{name}.py"
            )
            module = importlib_util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            loaded[name] = module
        yield loaded
    finally:
        for name, old in saved.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old


def desktop_bytes(desktop, tmp_path: Path, teacher_name: str, rows: list[dict]) -> bytes:
    """用桌面版导出器渲染同一批数据。"""
    records = [
        desktop["models"].Record(
            date=Date.fromisoformat(row["date"]),
            start_time=Time.fromisoformat(row["start_time"]),
            hours=row["hours"],
            class_type=row["class_type"],
            class_name=row["class_name"],
            note=row.get("note", ""),
        )
        for row in rows
    ]
    data = desktop["models"].MonthData(teacher_name=teacher_name, records=records)
    path = tmp_path / "desktop.xlsx"
    desktop["excel_exporter"].export(path, data)
    return path.read_bytes()


def server_bytes(teacher_name: str, rows: list[dict]) -> bytes:
    """服务端导出同一批数据 —— **rate 按桌面版的静态表填**（见模块 docstring）。"""
    return salary_excel.build_bytes(
        [
            TeacherSheet(
                teacher_name=teacher_name,
                rows=[
                    ExportRow(
                        date=Date.fromisoformat(row["date"]),
                        start_time=Time.fromisoformat(row["start_time"]),
                        hours=row["hours"],
                        rate=CLASS_RATES.get(row["class_type"], DEFAULT_RATE),
                        class_type=row["class_type"],
                        class_name=row["class_name"],
                        note=row.get("note", ""),
                    )
                    for row in rows
                ],
            )
        ],
        single=True,
    )


SYNTHETIC_ROWS = [
    # 两个班、日期与时间乱序（对拍同时验证排序），含空备注和带备注的
    {"date": "2026-09-05", "start_time": "14:00:00", "hours": 2.5,
     "class_type": "1对3", "class_name": "XB048N5", "note": "有2个试听"},
    {"date": "2026-09-03", "start_time": "19:15:00", "hours": 1.5,
     "class_type": "1对3", "class_name": "XB052N5", "note": ""},
    {"date": "2026-09-04", "start_time": "13:00:00", "hours": 2.5,
     "class_type": "1对1", "class_name": "YDE032N2", "note": ""},
    # 同一天、同一个班、同一时间两节 —— 排序的 tie 也要一致
    {"date": "2026-09-05", "start_time": "14:00:00", "hours": 1.0,
     "class_type": "1对3", "class_name": "XB048N5", "note": ""},
]


def test_与桌面版逐单元格一致(desktop, tmp_path):
    """★★ 合成数据对拍。CI 里也跑 —— 这条才是守着格式的那道闸。"""
    assert snapshot(server_bytes("梁筱", SYNTHETIC_ROWS)) == snapshot(
        desktop_bytes(desktop, tmp_path, "梁筱", SYNTHETIC_ROWS)
    )


@pytest.mark.skipif(not RECORDS_JSON.exists(), reason="没有桌面版真实数据")
def test_真实数据与桌面版逐单元格一致(desktop, tmp_path):
    """★ 拿 `dist/records.json`（真实生产数据）再对一遍。

    合成数据只能覆盖到我想到的形状；真实数据里有我没有的排列组合。
    ⚠️ 这份数据的班型都在 `CLASS_RATES` 表里，且是「排课后没改过费率」的月份 ——
       正好是能对得上的前提（见模块 docstring）。
    """
    raw = json.loads(RECORDS_JSON.read_text(encoding="utf-8"))

    assert snapshot(server_bytes(raw["teacher_name"], raw["records"])) == snapshot(
        desktop_bytes(desktop, tmp_path, raw["teacher_name"], raw["records"])
    )


# ── 表结构 ────────────────────────────────────────


@pytest.fixture
def one_lesson(client, make_class, make_lesson, make_user, headers_for):
    """一位老师、一节已完成的课 → 直接可下载的响应。"""
    klass = make_class(name="EXP001", class_type="1对1", rate=80.0)
    teacher = make_user("13900000201", role=Role.teacher, display_name="梁筱")
    make_lesson(
        klass=klass,
        teacher=teacher,
        lesson_date=Date(2026, 9, 3),
        start_time=Time(19, 15),
        hours=1.5,
        note="有1个试听",
        status=LessonStatus.completed,
    )
    return export(client, headers_for(teacher), month="2026-09")


def test_下载响应是xlsx且文件名带中文(one_lesson):
    assert one_lesson.status_code == 200
    assert one_lesson.headers["content-type"] == XLSX_MEDIA_TYPE

    disposition = one_lesson.headers["content-disposition"]
    # ⚠️ 中文文件名只能靠 RFC 5987 那份；`filename="salary.xlsx"` 是给老客户端的兜底
    assert "filename*=UTF-8''" in disposition
    assert quote("梁筱_工资结算表.xlsx", safe="") in disposition


def test_表头标题姓名与列宽(one_lesson):
    ws = load(one_lesson.content).active

    assert ws.title == "工资结算表"
    assert [str(r) for r in ws.merged_cells.ranges] == ["A1:J1"]
    assert ws["A1"].value == "工资结算表"
    assert ws["A1"].font.size == 16 and ws["A1"].font.bold

    assert ws["G2"].value == "姓名："
    assert ws["H2"].value == "梁筱"

    headers = [ws.cell(row=3, column=i).value for i in range(1, 11)]
    assert headers == HEADERS
    assert ws["A3"].fill.start_color.rgb == "FFBDD7EE"
    assert ws["A3"].font.bold

    widths = [ws.column_dimensions[chr(64 + i)].width for i in range(1, 11)]
    assert widths == COLUMN_WIDTHS


def test_数据行写公式而不是算好的数值(one_lesson):
    """★ F 列必须是 `=D4*E4`。

    写死数值就等于把「改课时/改费率自动重算」的能力弄丢了 —— 领导改一下小时数，
    薪酬那一格得跟着动。
    """
    ws = load(one_lesson.content).active

    assert ws["A4"].value == DateTime(2026, 9, 3)
    assert ws["B4"].value == "四"  # ⚠️ 是「四」不是「周四」
    assert ws["C4"].value == "19:15"  # 字符串，秒被丢掉
    assert ws["D4"].value == 1.5
    assert ws["E4"].value == 80.0
    assert ws["F4"].value == "=D4*E4"
    assert ws["J4"].value == "有1个试听"


def test_班级那列写的是班型不是班名(one_lesson):
    """★ I 列是「1对1」这种**班型** —— 班名只用来配色，不上表。"""
    ws = load(one_lesson.content).active

    assert ws["I4"].value == "1对1"
    assert "EXP001" not in [c.value for row in ws.iter_rows() for c in row]


def test_合计行公式覆盖所有数据行(
    client, make_class, make_lesson, make_user, headers_for
):
    klass = make_class(name="EXP002", class_type="1对3", rate=100.0)
    teacher = make_user("13900000202", role=Role.teacher, display_name="王五")
    for day, hours in ((Date(2026, 9, 3), 1.5), (Date(2026, 9, 10), 2.0), (Date(2026, 9, 20), 1.0)):
        make_lesson(
            klass=klass,
            teacher=teacher,
            lesson_date=day,
            hours=hours,
            status=LessonStatus.completed,
        )

    ws = load(export(client, headers_for(teacher), month="2026-09").content).active

    # 3 节 → 数据行 4~6，合计行 7
    assert ws["G7"].value == "=SUM(D4:D6)"
    assert ws["H7"].value == "=SUM(F4:F6)"
    assert ws["G7"].font.bold
    assert ws["A7"].value is None and ws["A7"].border.left.style == "thin"
    assert ws.max_row == 7


def test_颜色按班级名分组(
    client, make_class, make_lesson, make_user, headers_for
):
    """★ 同一个班上几次课就同色（不需要连续），换班换色，按排序后首现顺序发色。

    老师扫一眼就知道哪几行是同一个班的 —— 这是这张表唯一的视觉功能。
    """
    a = make_class(name="EXP003", class_type="1对1", rate=80.0)
    b = make_class(name="EXP004", class_type="1对3", rate=100.0)
    teacher = make_user("13900000203", role=Role.teacher, display_name="赵六")
    for klass, day in ((a, Date(2026, 9, 1)), (b, Date(2026, 9, 2)), (a, Date(2026, 9, 3))):
        make_lesson(
            klass=klass, teacher=teacher, lesson_date=day, status=LessonStatus.completed
        )

    content = export(client, headers_for(teacher), month="2026-09").content

    first, second, third = (fill_of(content, f"A{r}") for r in (4, 5, 6))
    assert first == third == COLOR_PALETTE[0]  # 班 A 首现 → 拿第一色，且两行同色
    assert second == COLOR_PALETTE[1]  # 班 B 换色
    assert first != second


# ── 权限 ──────────────────────────────────────────


def test_老师带别人的teacher_id也只导自己(
    client, make_class, make_lesson, make_user, headers_for
):
    """★ `teacher_id` 对老师直接忽略。

    不忽略的话，老师传个别人的 id 就能把同事的工资表拿走 ——
    跟 `list_lessons` 里「传啥都没用」是同一条规矩。
    """
    klass = make_class(name="EXP005")
    me = make_user("13900000204", role=Role.teacher, display_name="我")
    other = make_user("13900000205", role=Role.teacher, display_name="别人")
    make_lesson(klass=klass, teacher=me, hours=1.0, status=LessonStatus.completed)
    make_lesson(klass=klass, teacher=other, hours=9.0, status=LessonStatus.completed)

    ws = load(export(client, headers_for(me), teacher_id=other.id).content).active

    assert ws["H2"].value == "我"
    assert ws["H2"].value != "别人"


def test_未登录401(client):
    assert client.get(f"{EXPORT}?month=2026-09").status_code == 401


# ── 空数据 ────────────────────────────────────────


def test_空月份返回400不产文件(client, teacher_headers):
    resp = export(client, teacher_headers, month="2020-01")

    assert resp.status_code == 400
    assert "没有已完成" in resp.json()["detail"]


def test_没上过的课不算数(client, make_class, make_lesson, make_user, headers_for):
    """排了课但没完成 → 还是空的。跟「空月份」是同一条护栏。"""
    klass = make_class(name="EXP006")
    teacher = make_user("13900000206", role=Role.teacher)
    make_lesson(klass=klass, teacher=teacher, hours=2.0, status=LessonStatus.scheduled)

    assert export(client, headers_for(teacher)).status_code == 400


# ── 多人导出 ──────────────────────────────────────


def test_每位老师一个sheet(
    client, make_class, make_lesson, make_user, admin_headers, headers_for
):
    klass = make_class(name="EXP007")
    a = make_user("13900000207", role=Role.teacher, display_name="阿宝")
    b = make_user("13900000208", role=Role.teacher, display_name="小刚")
    make_lesson(klass=klass, teacher=a, hours=1.0, status=LessonStatus.completed)
    make_lesson(klass=klass, teacher=b, hours=2.0, status=LessonStatus.completed)

    wb = load(export(client, admin_headers).content)

    assert sorted(wb.sheetnames) == ["小刚", "阿宝"]
    assert wb["阿宝"]["H2"].value == "阿宝"
    assert wb["小刚"]["H2"].value == "小刚"


def test_当月零课的老师不建sheet(
    client, make_class, make_lesson, make_user, admin_headers
):
    """一张只有标题和表头的空表是噪音 —— 不给它建 sheet。"""
    klass = make_class(name="EXP008")
    taught = make_user("13900000209", role=Role.teacher, display_name="上课的")
    silent = make_user("13900000210", role=Role.teacher, display_name="没上课的")
    make_lesson(klass=klass, teacher=taught, hours=1.0, status=LessonStatus.completed)
    make_lesson(klass=klass, teacher=silent, hours=1.0, status=LessonStatus.scheduled)

    wb = load(export(client, admin_headers).content)

    assert wb.sheetnames == ["上课的"]


def test_多人导出文件名带月份(client, make_class, make_lesson, make_user, admin_headers):
    klass = make_class(name="EXP009")
    teacher = make_user("13900000211", role=Role.teacher)
    make_lesson(klass=klass, teacher=teacher, hours=1.0, status=LessonStatus.completed)

    disposition = export(client, admin_headers).headers["content-disposition"]

    assert quote(f"工资结算表_{DEFAULT_MONTH}.xlsx", safe="") in disposition


def test_管理员可以只导一位老师(
    client, make_class, make_lesson, make_user, admin_headers
):
    klass = make_class(name="EXP010")
    a = make_user("13900000212", role=Role.teacher, display_name="甲")
    b = make_user("13900000213", role=Role.teacher, display_name="乙")
    make_lesson(klass=klass, teacher=a, hours=1.0, status=LessonStatus.completed)
    make_lesson(klass=klass, teacher=b, hours=1.0, status=LessonStatus.completed)

    wb = load(export(client, admin_headers, teacher_id=b.id).content)

    assert wb.sheetnames == ["工资结算表"]  # 单人仍是固定表名（与桌面版一致）
    assert wb.active["H2"].value == "乙"


def test_导不存在的老师返回404(client, admin_headers):
    assert export(client, admin_headers, teacher_id=999999).status_code == 404


# ── sheet 名清洗 ──────────────────────────────────
# Excel 对 sheet 名有硬约束，撞上 openpyxl 直接抛异常 —— 一年一度的交报表
# 不能因为某个老师名字里带个 `[` 就 500。


def test_sheet名清掉非法字符并截长(
    client, make_class, make_lesson, make_user, admin_headers
):
    klass = make_class(name="EXP011")
    weird = make_user("13900000214", role=Role.teacher, display_name="张[三]:李/四" + "长" * 40)
    make_lesson(klass=klass, teacher=weird, hours=1.0, status=LessonStatus.completed)

    wb = load(export(client, admin_headers).content)
    title = wb.sheetnames[0]

    assert len(title) <= 31
    assert not set(title) & set(r":\/?*[]")
    assert wb[title]["H2"].value == weird.display_name  # 表里的姓名仍是原文


def test_同名两位老师不会合并成一张表(
    client, make_class, make_lesson, make_user, admin_headers
):
    """★ 重名的两位老师**各留一张**，后一张加 `(2)`。

    合并的话两个人的工资就加进同一张表了 —— 那是少发一个人的钱。
    """
    klass = make_class(name="EXP012")
    first = make_user("13900000215", role=Role.teacher, display_name="李四")
    second = make_user("13900000216", role=Role.teacher, display_name="李四")
    make_lesson(klass=klass, teacher=first, hours=1.0, status=LessonStatus.completed)
    make_lesson(klass=klass, teacher=second, hours=2.0, status=LessonStatus.completed)

    wb = load(export(client, admin_headers).content)

    assert sorted(wb.sheetnames) == ["李四", "李四(2)"]
    assert [wb[name]["H2"].value for name in wb.sheetnames] == ["李四", "李四"]


# ── 停用的老师 ────────────────────────────────────


def test_停用的老师仍然导得出来(
    client, session, make_class, make_lesson, make_user, admin_headers
):
    """★ 离职老师的工资是**欠着人家的**，必须还能导。

    ⚠️ 所以查人时**不能**用 `get_active_teacher_or_400`（那个要求 is_active）。
    """
    klass = make_class(name="EXP013")
    teacher = make_user("13900000217", role=Role.teacher, display_name="离职的")
    make_lesson(klass=klass, teacher=teacher, hours=4.0, status=LessonStatus.completed)

    teacher.is_active = False
    session.add(teacher)
    session.commit()

    wb = load(export(client, admin_headers, teacher_id=teacher.id).content)

    assert wb.active["H2"].value == "离职的"
    assert wb.active["D4"].value == 4.0
