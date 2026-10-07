"""课程：排课 / 列表 / 改课 / 删除 / 权限（实施计划 5.5）。

完成上课与考勤的事务在 test_attendance.py。
"""

from sqlalchemy import func
from sqlmodel import select

import pytest

from app.models import HourTransaction, Lesson, LessonStatus, Role


def status_of(session, lesson_id: int) -> LessonStatus:
    """重新查一次状态。

    ⚠️ 不能用夹具返回的那个 Lesson 实例：HTTP 请求是在**另一个 session** 里提交的，
    本 session 的身份映射里那个对象还停在旧状态。
    """
    return session.exec(select(Lesson.status).where(Lesson.id == lesson_id)).one()


def lesson_count(session) -> int:
    return session.exec(select(func.count()).select_from(Lesson)).one()


@pytest.fixture
def admin(make_user):
    return make_user("13900000010", role=Role.admin)


@pytest.fixture
def teacher(make_user):
    return make_user("13900000011", role=Role.teacher)


@pytest.fixture
def other_teacher(make_user):
    return make_user("13900000012", role=Role.teacher)


@pytest.fixture
def klass(make_class):
    return make_class()


def payload_for(klass, teacher, **overrides) -> dict:
    payload = {
        "class_id": klass.id,
        "teacher_id": teacher.id,
        "date": "2026-10-05",
        "start_time": "09:00",
        "hours": 1.0,
        "note": "",
    }
    payload.update(overrides)
    return payload


# ── 排课 ──────────────────────────────────────────


def test_排课成功并带上班级名和老师名(client, admin, teacher, klass, headers_for):
    resp = client.post(
        "/api/lessons",
        json=payload_for(klass, teacher, hours=1.5),
        headers=headers_for(admin),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["class_name"] == klass.name
    assert body["teacher_name"] == teacher.display_name
    assert body["status"] == "scheduled"
    assert body["hours"] == 1.5


def test_排课时费率从班级快照抄一份(client, admin, teacher, klass, headers_for, session):
    """★ 客户端传 rate 必须**被忽略** —— 否则谁都能给自己开 999 元/时。"""
    resp = client.post(
        "/api/lessons",
        json=payload_for(klass, teacher, rate=999.0),
        headers=headers_for(admin),
    )
    assert resp.status_code == 201
    assert resp.json()["rate"] == 80.0

    lesson = session.get(Lesson, resp.json()["id"])
    session.refresh(lesson)
    assert lesson.rate == 80.0


def test_排课后改班级费率不影响这节课(client, admin, teacher, klass, headers_for, session):
    resp = client.post(
        "/api/lessons", json=payload_for(klass, teacher), headers=headers_for(admin)
    )
    lesson_id = resp.json()["id"]

    klass.rate = 200.0
    session.add(klass)
    session.commit()

    lesson = session.get(Lesson, lesson_id)
    session.refresh(lesson)
    assert lesson.rate == 80.0


def test_老师不能排课(client, teacher, klass, headers_for):
    resp = client.post(
        "/api/lessons", json=payload_for(klass, teacher), headers=headers_for(teacher)
    )
    assert resp.status_code == 403


def test_未登录不能排课(client, teacher, klass):
    resp = client.post("/api/lessons", json=payload_for(klass, teacher))
    assert resp.status_code == 401


def test_课时必须大于0(client, admin, teacher, klass, headers_for):
    resp = client.post(
        "/api/lessons",
        json=payload_for(klass, teacher, hours=0),
        headers=headers_for(admin),
    )
    assert resp.status_code == 400
    assert "课时" in resp.json()["detail"]


def test_不能排给已停用的老师(client, admin, teacher, klass, headers_for, session):
    teacher.is_active = False
    session.add(teacher)
    session.commit()

    resp = client.post(
        "/api/lessons", json=payload_for(klass, teacher), headers=headers_for(admin)
    )
    assert resp.status_code == 400
    assert "已停用" in resp.json()["detail"]


def test_不能给已停用的班级排课(client, admin, teacher, klass, headers_for, session):
    klass.is_active = False
    session.add(klass)
    session.commit()

    resp = client.post(
        "/api/lessons", json=payload_for(klass, teacher), headers=headers_for(admin)
    )
    assert resp.status_code == 400
    assert "停用" in resp.json()["detail"]


def test_班级不存在返回404(client, admin, teacher, headers_for):
    resp = client.post(
        "/api/lessons",
        json=payload_for(type("K", (), {"id": 9999})(), teacher),
        headers=headers_for(admin),
    )
    # payload_for 只需要 klass.id，用一个假对象就够
    assert resp.status_code == 404
    assert resp.json()["detail"] == "班级不存在"


# ── 列表 ──────────────────────────────────────────


def test_管理员看到全部老师(client, admin, teacher, other_teacher, klass, headers_for, make_lesson):
    make_lesson(klass=klass, teacher=teacher)
    make_lesson(klass=klass, teacher=other_teacher)

    resp = client.get("/api/lessons", headers=headers_for(admin))
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_老师只看到自己的课(client, teacher, other_teacher, klass, headers_for, make_lesson):
    mine = make_lesson(klass=klass, teacher=teacher)
    make_lesson(klass=klass, teacher=other_teacher)

    resp = client.get("/api/lessons", headers=headers_for(teacher))
    assert resp.status_code == 200
    assert [row["id"] for row in resp.json()] == [mine.id]


def test_老师传别人的teacher_id也翻不到别人的课(
    client, teacher, other_teacher, klass, headers_for, make_lesson
):
    """★ 参数对老师直接忽略 —— 否则传个 id 就能翻遍全校课表。"""
    mine = make_lesson(klass=klass, teacher=teacher)
    make_lesson(klass=klass, teacher=other_teacher)

    resp = client.get(
        f"/api/lessons?teacher_id={other_teacher.id}", headers=headers_for(teacher)
    )
    assert resp.status_code == 200
    assert [row["id"] for row in resp.json()] == [mine.id]


def test_按日期过滤(client, admin, teacher, klass, headers_for, make_lesson):
    from datetime import date

    keep = make_lesson(klass=klass, teacher=teacher, lesson_date=date(2026, 10, 5))
    make_lesson(klass=klass, teacher=teacher, lesson_date=date(2026, 10, 6))

    resp = client.get("/api/lessons?date=2026-10-05", headers=headers_for(admin))
    assert [row["id"] for row in resp.json()] == [keep.id]


def test_按月过滤(client, admin, teacher, klass, headers_for, make_lesson):
    from datetime import date

    keep = make_lesson(klass=klass, teacher=teacher, lesson_date=date(2026, 10, 31))
    make_lesson(klass=klass, teacher=teacher, lesson_date=date(2026, 11, 1))

    resp = client.get("/api/lessons?month=2026-10", headers=headers_for(admin))
    assert [row["id"] for row in resp.json()] == [keep.id]


def test_月末是各类月份的最后一个自然日(client, admin, teacher, klass, headers_for, make_lesson):
    """2 月 28 天、闰年 29 天都要算对，别写成固定 30/31。"""
    from datetime import date

    keep = make_lesson(klass=klass, teacher=teacher, lesson_date=date(2028, 2, 29))
    resp = client.get("/api/lessons?month=2028-02", headers=headers_for(admin))
    assert [row["id"] for row in resp.json()] == [keep.id]


def test_month参数格式不对返回400(client, admin, headers_for):
    resp = client.get("/api/lessons?month=2026/10", headers=headers_for(admin))
    assert resp.status_code == 400


# ── 详情权限 ───────────────────────────────────────


def test_老师看别人的课返回403(client, teacher, other_teacher, klass, headers_for, make_lesson):
    lesson = make_lesson(klass=klass, teacher=other_teacher)
    resp = client.get(f"/api/lessons/{lesson.id}", headers=headers_for(teacher))
    assert resp.status_code == 403


def test_详情带出名单和余额(client, admin, teacher, klass, headers_for, make_lesson, make_student, enroll):
    student = make_student(name="小明")
    enroll(klass, student)
    lesson = make_lesson(klass=klass, teacher=teacher)

    resp = client.get(f"/api/lessons/{lesson.id}", headers=headers_for(admin))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["students"]) == 1
    # 还没点名 → status 为 None，前端据此默认高亮「出勤」
    assert body["students"][0]["status"] is None
    assert body["students"][0]["remaining_hours"] == 0.0
    # 班型要透出去：前端拿它标「按当前勾选：不扣课时」用的是同一个口径
    assert body["class_type"] == klass.class_type


# ── 改课 ──────────────────────────────────────────


def test_改课成功(client, admin, teacher, klass, headers_for, make_lesson, session):
    lesson = make_lesson(klass=klass, teacher=teacher)
    resp = client.patch(
        f"/api/lessons/{lesson.id}",
        json={"date": "2026-10-08", "hours": 2.0},
        headers=headers_for(admin),
    )
    assert resp.status_code == 200
    assert resp.json()["lesson_date"] == "2026-10-08"
    assert resp.json()["hours"] == 2.0


def test_改课不能动费率(client, admin, teacher, klass, headers_for, make_lesson):
    lesson = make_lesson(klass=klass, teacher=teacher)
    resp = client.patch(
        f"/api/lessons/{lesson.id}", json={"rate": 999}, headers=headers_for(admin)
    )
    assert resp.status_code == 200
    assert resp.json()["rate"] == 80.0


def test_老师不能改课(client, teacher, klass, headers_for, make_lesson):
    lesson = make_lesson(klass=klass, teacher=teacher)
    resp = client.patch(
        f"/api/lessons/{lesson.id}", json={"hours": 2.0}, headers=headers_for(teacher)
    )
    assert resp.status_code == 403


# ── 删除 ──────────────────────────────────────────


def test_删除已排课的课是真删(client, admin, teacher, klass, headers_for, make_lesson, session):
    lesson = make_lesson(klass=klass, teacher=teacher)
    resp = client.delete(f"/api/lessons/{lesson.id}", headers=headers_for(admin))
    assert resp.status_code == 200
    assert lesson_count(session) == 0


def test_已完成的课不能删只能取消(client, admin, teacher, klass, headers_for, make_lesson, session):
    """★ 也顺带挡住「改已完成课的 hours」那条路 —— 账会和流水对不上。"""
    lesson = make_lesson(klass=klass, teacher=teacher)
    lesson.status = LessonStatus.completed
    session.add(lesson)
    session.commit()

    resp = client.delete(f"/api/lessons/{lesson.id}", headers=headers_for(admin))
    assert resp.status_code == 409
    assert lesson_count(session) == 1


def test_老师不能删课(client, teacher, klass, headers_for, make_lesson):
    lesson = make_lesson(klass=klass, teacher=teacher)
    resp = client.delete(f"/api/lessons/{lesson.id}", headers=headers_for(teacher))
    assert resp.status_code == 403


def test_课程不存在返回404(client, admin, headers_for):
    assert client.get("/api/lessons/9999", headers=headers_for(admin)).status_code == 404
    assert (
        client.delete("/api/lessons/9999", headers=headers_for(admin)).status_code == 404
    )


def test_排课不产生任何课时流水(client, admin, teacher, klass, headers_for, session, make_student, enroll):
    """排课只是安排，钱还没动。"""
    student = make_student(name="小明")
    enroll(klass, student)

    client.post(
        "/api/lessons", json=payload_for(klass, teacher), headers=headers_for(admin)
    )

    total = session.exec(select(func.count()).select_from(HourTransaction)).one()
    assert total == 0
