"""计薪统计（Phase 4）。

钱算得对不对全看这几个用例。口径：只算 `status='completed'` 的课，
课时费 = `hours × lessons.rate`（**快照**），月份两端都含。
"""

from datetime import date as Date
from datetime import time as Time

import pytest

from app.models import LessonStatus, Role

MY = "/api/attendance/my"
SUMMARY = "/api/attendance/summary"
EXPORT = "/api/attendance/export"


def my(client, headers, month="2026-10"):
    return client.get(f"{MY}?month={month}", headers=headers)


def summary(client, headers, month="2026-10"):
    return client.get(f"{SUMMARY}?month={month}", headers=headers)


# ── 口径：算哪些课 ────────────────────────────────


def test_只算已完成的课(client, session, make_class, make_lesson, make_user, headers_for):
    """scheduled / cancelled 都不进统计 —— 没上过的课不发钱。"""
    klass = make_class(name="PAY001")
    teacher = make_user("13900000101", role=Role.teacher)
    make_lesson(klass=klass, teacher=teacher, hours=2.0, status=LessonStatus.completed)
    make_lesson(klass=klass, teacher=teacher, hours=4.0, status=LessonStatus.scheduled)
    make_lesson(klass=klass, teacher=teacher, hours=8.0, status=LessonStatus.cancelled)

    body = my(client, headers_for(teacher)).json()

    assert body["total_hours"] == 2.0
    assert len(body["lessons"]) == 1


def test_课时费用快照不跟班级费率漂移(
    client, session, make_lesson, make_user, make_class, headers_for
):
    """★ 排课后改班级费率，**已经上过的课**按快照算，一分钱都不变。

    这是全项目的硬规则：改一次费率不该篡改历史工资表。反过来说，
    要是这里用了 `classes.rate`，老板改个费率就会把上个月的报表一起改掉。
    """
    klass = make_class(name="YDY900", class_type="1对1", rate=80.0)
    teacher = make_user("13900000102", role=Role.teacher)
    make_lesson(
        klass=klass, teacher=teacher, hours=1.5, status=LessonStatus.completed
    )

    before = my(client, headers_for(teacher)).json()
    assert before["total_salary"] == 120.0  # 1.5 × 80

    # 费率翻几倍，历史不变
    klass.rate = 999.0
    session.add(klass)
    session.commit()

    after = my(client, headers_for(teacher)).json()
    assert after["lessons"][0]["rate"] == 80.0
    assert after["total_salary"] == 120.0


def test_认不出的班型照样算(client, session, make_lesson, make_user, make_class, headers_for):
    """自定义班型（VIP / 冲刺班）走它自己的快照费率，**不是** DEFAULT_RATE。"""
    klass = make_class(name="VIP001", class_type="VIP", rate=95.0)
    teacher = make_user("13900000103", role=Role.teacher)
    make_lesson(
        klass=klass, teacher=teacher, hours=2.0, status=LessonStatus.completed
    )

    body = my(client, headers_for(teacher)).json()

    assert body["lessons"][0]["class_type"] == "VIP"
    assert body["lessons"][0]["rate"] == 95.0
    assert body["total_salary"] == 190.0


# ── 月份边界 ──────────────────────────────────────


def test_月份两端都算进去(client, session, make_class, make_lesson, make_user, headers_for):
    """10-01 和 10-31 都算；9-30 和 11-01 都不算。

    ⚠️ 边界写成 `>` / `<` 就会把月初月末那两天漏掉 —— 而「上个月最后一天」
       正是最容易被漏掉的那种。
    """
    klass = make_class(name="PAY002")
    teacher = make_user("13900000104", role=Role.teacher)
    for day, hours in [
        (Date(2026, 9, 30), 1.0),
        (Date(2026, 10, 1), 2.0),
        (Date(2026, 10, 31), 4.0),
        (Date(2026, 11, 1), 8.0),
    ]:
        make_lesson(
            klass=klass,
            teacher=teacher,
            lesson_date=day,
            hours=hours,
            status=LessonStatus.completed,
        )

    body = my(client, headers_for(teacher), month="2026-10").json()

    assert body["total_hours"] == 6.0
    assert [lesson["lesson_date"] for lesson in body["lessons"]] == [
        "2026-10-01",
        "2026-10-31",
    ]


def test_月份格式不对返回400(client, teacher_headers):
    # ⚠️ `2026-1` **不算错** —— month_bounds 不强制补零，它就是 2026 年 1 月。
    for bad in ("2026-13", "2026-00", "abc", "2026/10", ""):
        resp = my(client, teacher_headers, month=bad)
        assert resp.status_code == 400, bad
        assert "YYYY-MM" in resp.json()["detail"]


def test_月份缺省是422而不是悄悄给个默认(client, teacher_headers, admin_headers):
    """★ `month` 必填。

    服务器时区若是 UTC，在月初 00:00~08:00 把「省略」解释成「当月」会算成上个月。
    月份一律由前端按本地时间算好传进来（跟前端不能用 toISOString 取今天是同一回事）。
    """
    assert client.get(MY, headers=teacher_headers).status_code == 422
    assert client.get(SUMMARY, headers=admin_headers).status_code == 422


def test_当月没课返回零而不是404(client, teacher_headers):
    body = my(client, teacher_headers, month="2020-01").json()

    assert body["total_hours"] == 0.0
    assert body["total_salary"] == 0.0
    assert body["lessons"] == []


# ── 权限与隔离 ────────────────────────────────────


def test_老师只看得到自己的课(
    client, session, make_class, make_lesson, make_user, headers_for
):
    """★ 别的老师上多少课，跟我这个接口无关。"""
    klass = make_class(name="PAY003")
    me = make_user("13900000105", role=Role.teacher)
    other = make_user("13900000106", role=Role.teacher)
    make_lesson(klass=klass, teacher=me, hours=2.0, status=LessonStatus.completed)
    make_lesson(klass=klass, teacher=other, hours=100.0, status=LessonStatus.completed)

    body = my(client, headers_for(me)).json()

    assert body["total_hours"] == 2.0
    assert body["teacher_id"] == me.id


def test_管理员调我的也只返回自己的(
    client, session, make_class, make_lesson, make_user, headers_for
):
    """管理员自己带课也走 `/my` —— 授课人不限角色，排课能指定给任何启用账号。

    这里断言的是**不会**因为角色是管理员就把全机构的课都算到「我的」头上。
    """
    klass = make_class(name="PAY004")
    admin = make_user("13900000107", role=Role.admin)
    teacher = make_user("13900000108", role=Role.teacher)
    make_lesson(klass=klass, teacher=admin, hours=3.0, status=LessonStatus.completed)
    make_lesson(klass=klass, teacher=teacher, hours=50.0, status=LessonStatus.completed)

    body = my(client, headers_for(admin)).json()

    assert body["total_hours"] == 3.0


def test_老师调汇总返回403(client, teacher_headers):
    assert summary(client, teacher_headers).status_code == 403


def test_未登录三个接口都401(client):
    assert client.get(f"{MY}?month=2026-10").status_code == 401
    assert client.get(f"{SUMMARY}?month=2026-10").status_code == 401
    assert client.get(f"{EXPORT}?month=2026-10").status_code == 401


# ── 汇总 ──────────────────────────────────────────


def test_管理员汇总列出每位老师(
    client, session, make_class, make_lesson, make_user, headers_for
):
    klass = make_class(name="PAY005")
    a = make_user("13900000109", role=Role.teacher)
    b = make_user("13900000110", role=Role.teacher)
    make_lesson(klass=klass, teacher=a, hours=2.0, status=LessonStatus.completed)
    make_lesson(klass=klass, teacher=a, hours=3.0, status=LessonStatus.completed)
    make_lesson(klass=klass, teacher=b, hours=1.0, status=LessonStatus.completed)

    body = summary(client, headers_for(make_user("13900000111", role=Role.admin))).json()

    assert body["teacher_count"] == 2
    by_id = {t["teacher_id"]: t for t in body["teachers"]}
    assert by_id[a.id]["lesson_count"] == 2
    assert by_id[a.id]["total_hours"] == 5.0
    assert by_id[b.id]["total_hours"] == 1.0


def test_汇总不列当月没上课的老师(
    client, session, make_lesson, make_user, headers_for
):
    """只列当月有已完成课的老师 —— 导出的 sheet 名单跟这份一致。"""
    taught = make_user("13900000112", role=Role.teacher)
    make_user("13900000113", role=Role.teacher)  # 一节没上
    make_lesson(teacher=taught, hours=1.0, status=LessonStatus.completed)

    body = summary(client, headers_for(make_user("13900000114", role=Role.admin))).json()

    assert [t["teacher_id"] for t in body["teachers"]] == [taught.id]


def test_停用的老师仍然出现在汇总里(
    client, session, make_lesson, make_user, headers_for
):
    """★ 停用只挡「登不进来」，不挡「查历史的账」。

    老师离职了，他这个月的工资是**欠着人家的**，必须还能出现在汇总和导出里。
    ⚠️ 所以这里**不能**复用 `get_active_teacher_or_400`（那个要求 is_active）。
    """
    teacher = make_user("13900000115", role=Role.teacher)
    make_lesson(teacher=teacher, hours=4.0, status=LessonStatus.completed)

    teacher.is_active = False
    session.add(teacher)
    session.commit()

    body = summary(client, headers_for(make_user("13900000116", role=Role.admin))).json()

    assert [t["teacher_id"] for t in body["teachers"]] == [teacher.id]
    assert body["teachers"][0]["total_hours"] == 4.0


def test_汇总数字等于明细逐行相加(
    client, session, make_class, make_lesson, make_user, headers_for
):
    """★ 屏幕上的汇总和导出表里的那一格，必须出自同一批数字。

    这正是把 `/my`、`/summary`、`/export` 都接到同一个 `month_rows()` 上的原因。
    """
    klass = make_class(name="PAY006")
    teacher = make_user("13900000117", role=Role.teacher)
    for hours in (1.5, 2.0, 2.5, 3.0):
        make_lesson(
            klass=klass, teacher=teacher, hours=hours, status=LessonStatus.completed
        )

    mine = my(client, headers_for(teacher)).json()
    overview = summary(client, headers_for(make_user("13900000118", role=Role.admin))).json()

    row_sum = sum(lesson["salary"] for lesson in mine["lessons"])
    assert mine["total_salary"] == pytest.approx(row_sum, abs=0.01)
    assert overview["total_salary"] == pytest.approx(mine["total_salary"], abs=0.01)
    assert overview["teachers"][0]["total_salary"] == mine["total_salary"]


def test_学生课时流水不影响计薪(
    client, session, make_lesson, make_student, make_user, fund, headers_for
):
    """★ 三种「课时」不能混：教师课时费 / 班级已上课时 / 学生独立余额。

    学生充值和扣课时跟老师的工资是两本账 —— 这里锁住「学生的课时动了，
    老师这边的数字一动不动」。
    """
    teacher = make_user("13900000119", role=Role.teacher)
    make_lesson(teacher=teacher, hours=2.0, status=LessonStatus.completed)
    student = make_student(name="小明")
    fund(student, amount=48.0)

    body = my(client, headers_for(teacher)).json()

    assert body["total_hours"] == 2.0
    assert body["total_salary"] == 160.0
