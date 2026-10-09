"""计薪统计 —— 只读，不发一条写语句。

★ **全系统只有这里一条计薪查询**，`/attendance/my`、`/attendance/summary`、
  `/attendance/export` 三处都从它出数。`docs/实施计划.md` §5.6 特意写了
  「计薪口径要和导出一起做，分开写必然两边对不上」——
  结构上兑现这句话的办法就是：**先把明细行查出来，汇总由明细行现加**。
  不写 `GROUP BY` 聚合，因为那会引入第二种口径（SQL 先乘再舍 vs Python 逐行舍再加）。

⚠️ 薪资只能用 `lessons.rate`（排课时的快照），**绝不 JOIN `classes.rate`**。
   改一次班级费率不该篡改历史工资表 —— 这是全项目的硬规则。

⚠️ 与别的 service 一样：**不 commit**（这里全是只读，本来也不需要）。
"""

from dataclasses import dataclass
from datetime import date as Date
from datetime import time as Time

from sqlmodel import Session, select

from app.exporters.salary_excel import ExportRow, TeacherSheet
from app.models import Class, Lesson, LessonStatus, User
from app.services.lessons import month_bounds


@dataclass(frozen=True)
class PayrollRow:
    """一节已完成的课。纯数据，不挂 ORM 对象出去。"""

    lesson_id: int
    teacher_id: int
    teacher_name: str
    lesson_date: Date
    start_time: Time
    hours: float
    rate: float  # ★ lessons.rate 快照
    class_id: int
    class_name: str
    class_type: str
    note: str

    @property
    def salary(self) -> float:
        """**这一节**的课时费，供逐节明细显示。

        与桌面版 `models.Record.salary` 同口径（逐节四舍五入）。
        ⚠️ 它**不**用来算合计 —— 见 `totals()` 的说明。
        """
        return round(self.hours * self.rate, 2)


@dataclass(frozen=True)
class TeacherTotals:
    teacher_id: int
    teacher_name: str
    lesson_count: int
    total_hours: float
    total_salary: float


def totals(rows: list[PayrollRow]) -> tuple[float, float]:
    """→ (课时数, 课时费)。

    ★ 课时费是 `round(sum(hours * rate), 2)` —— **先乘、求和、最后才舍入**，
      不是「逐节舍入后再相加」。因为 Excel 里合计那一格是 `=SUM(F4:Fn)`，
      而 F 是每行的 `=D*E`（未舍入的乘积），Excel 求和时用的就是未舍入值。
      这样屏幕上的数字才和下载下来的表里那一格对得上。
      两者的差别只在极端浮点下的一分钱，但**能对上**比「差不多」值得。
    """
    total_hours = round(sum(r.hours for r in rows), 2)
    total_salary = round(sum(r.hours * r.rate for r in rows), 2)
    return total_hours, total_salary


def month_rows(
    session: Session,
    *,
    month: str,
    teacher_id: int | None = None,
) -> list[PayrollRow]:
    """某月所有**已完成**的课，按老师、日期、时间排序。

    `teacher_id=None` → 全体老师（一条查询查完，避免 N+1）。
    """
    first, last = month_bounds(month)  # 格式不对会 400

    statement = (
        select(
            Lesson.id,
            Lesson.teacher_id,
            User.display_name,
            Lesson.lesson_date,
            Lesson.start_time,
            Lesson.hours,
            Lesson.rate,  # ★ 快照列 —— Class 只 JOIN 名字和班型，物理上够不着 classes.rate
            Class.id,
            Class.name,
            Class.class_type,
            Lesson.note,
        )
        .join(Class, Class.id == Lesson.class_id)
        .join(User, User.id == Lesson.teacher_id)
        .where(
            Lesson.status == LessonStatus.completed,
            Lesson.lesson_date >= first,  # 月初当天算
            Lesson.lesson_date <= last,  # 月末当天也算
        )
        # 前面两个键决定多人导出时 sheet 的顺序；后面三个是组内顺序，
        # 与桌面版 sorted_records() 的 (date, start_time) 对齐，
        # 末尾补 id 只是为了「同一天同一时间两节课」这个平局有个确定答案。
        .order_by(
            User.display_name,
            User.id,
            Lesson.lesson_date,
            Lesson.start_time,
            Lesson.id,
        )
    )
    if teacher_id is not None:
        statement = statement.where(Lesson.teacher_id == teacher_id)

    return [
        PayrollRow(
            lesson_id=lesson_id,
            teacher_id=tid,
            teacher_name=name,
            lesson_date=lesson_date,
            start_time=start_time,
            hours=hours,
            rate=rate,
            class_id=class_id,
            class_name=class_name,
            class_type=class_type,
            note=note,
        )
        for (
            lesson_id, tid, name, lesson_date, start_time,
            hours, rate, class_id, class_name, class_type, note,
        ) in session.exec(statement).all()
    ]


def group_by_teacher(rows: list[PayrollRow]) -> list[tuple[int, str, list[PayrollRow]]]:
    """按老师分组，**保持查询给出的顺序**（dict 有序）。

    → [(teacher_id, teacher_name, 该老师的行)]
    """
    buckets: dict[int, list[PayrollRow]] = {}
    for row in rows:
        buckets.setdefault(row.teacher_id, []).append(row)
    return [(tid, group[0].teacher_name, group) for tid, group in buckets.items()]


def teacher_totals(rows: list[PayrollRow]) -> list[TeacherTotals]:
    return [
        TeacherTotals(
            teacher_id=tid,
            teacher_name=name,
            lesson_count=len(group),
            total_hours=hours,
            total_salary=salary,
        )
        for tid, name, group in group_by_teacher(rows)
        for hours, salary in [totals(group)]
    ]


def to_sheets(rows: list[PayrollRow]) -> list[TeacherSheet]:
    """明细行 → 导出用的分表数据。**和上面的汇总用的是同一批行。**"""
    return [
        TeacherSheet(
            teacher_name=name,
            rows=[
                ExportRow(
                    date=r.lesson_date,
                    start_time=r.start_time,
                    hours=r.hours,
                    rate=r.rate,
                    class_type=r.class_type,
                    class_name=r.class_name,
                    note=r.note,
                )
                for r in group
            ],
        )
        for _, name, group in group_by_teacher(rows)
    ]
