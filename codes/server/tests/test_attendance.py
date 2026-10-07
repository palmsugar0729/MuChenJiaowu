"""★ 完成上课 / 取消 / 考勤 —— 扣课时的核心事务（实施计划 4.1 / 4.2）。

这几条错了就是钱错：扣多少、谁被扣、能不能重复扣、取消退不退款。
"""

from datetime import date as Date
from types import SimpleNamespace

import pytest
from sqlalchemy import func
from sqlmodel import select

from app.models import (
    Attendance,
    AttendanceStatus,
    HourTransaction,
    Lesson,
    LessonStatus,
    Role,
    TxnType,
)


def balance_of(session, student_id: int) -> float:
    """与 services/students.get_balance 同口径。"""
    return session.exec(
        select(func.coalesce(func.sum(HourTransaction.amount), 0.0)).where(
            HourTransaction.student_id == student_id
        )
    ).one()


def spent(session, student_id: int) -> float:
    """只算**消耗**流水的合计。

    大多数用例关心的是「这节课扣没扣、扣了多少」，而不是余额本身 ——
    余额里还混着夹具给的那笔起始课时。分开算断言才读得懂。
    """
    return session.exec(
        select(func.coalesce(func.sum(HourTransaction.amount), 0.0)).where(
            HourTransaction.student_id == student_id,
            HourTransaction.type == TxnType.consume,
        )
    ).one()


def status_of(session, lesson_id: int) -> LessonStatus:
    return session.exec(select(Lesson.status).where(Lesson.id == lesson_id)).one()


def content_of(session, lesson_id: int) -> str:
    """查单列而不是 session.get(Lesson, ...)。

    ⚠️ 接口在**另一个 Session** 里改了这行，测试这个 Session 的 identity map
       里还留着旧对象 —— `session.get` 会原样返回它，看起来就像「没写进去」。
       跟 `status_of` 一样查列，绕开这个缓存。
    """
    return session.exec(select(Lesson.content).where(Lesson.id == lesson_id)).one()


def consume_rows(session, lesson_id: int) -> list[HourTransaction]:
    return list(
        session.exec(
            select(HourTransaction).where(
                HourTransaction.lesson_id == lesson_id,
                HourTransaction.type == TxnType.consume,
            )
        ).all()
    )


def attendance_rows(session, lesson_id: int) -> list[Attendance]:
    return list(
        session.exec(select(Attendance).where(Attendance.lesson_id == lesson_id)).all()
    )


def total_rows(session) -> int:
    return session.exec(select(func.count()).select_from(HourTransaction)).one()


@pytest.fixture
def scene(make_class, make_student, make_user, make_lesson, enroll, fund):
    """一个典型场景：一个班、一位老师、两个在册学生、一节 2.5 小时的课。

    带 **10 课时** 起始余额 —— 2.5 的课扣得动，断言写出来也好看
    （10 - 2.5 = 7.5）。没有课时的话「完成上课」会被余额校验直接拦掉。
    """
    klass = make_class()
    teacher = make_user("13900000021", role=Role.teacher)
    xiaoming = fund(make_student(name="小明"))
    xiaohong = fund(make_student(name="小红"))
    enroll(klass, xiaoming)
    enroll(klass, xiaohong)
    lesson = make_lesson(klass=klass, teacher=teacher, hours=2.5)
    return SimpleNamespace(
        klass=klass,
        teacher=teacher,
        xiaoming=xiaoming,
        xiaohong=xiaohong,
        lesson=lesson,
    )


DEFAULT_CONTENT = "第三章 语法复盘"


def complete(client, headers, lesson_id, items=None, content=DEFAULT_CONTENT):
    """完成上课。`content` 必填，所以默认塞一句进去。"""
    body = {"items": items or []}
    if content is not None:
        body["content"] = content
    return client.post(f"/api/lessons/{lesson_id}/complete", json=body, headers=headers)


def set_attendance(client, headers, lesson_id, items, content=None):
    body = {"items": items}
    if content is not None:
        body["content"] = content
    return client.post(
        f"/api/lessons/{lesson_id}/attendance", json=body, headers=headers
    )


# ── ★ 完成上课 ─────────────────────────────────────


def test_完成上课给每个在册学生扣课时(client, session, scene, headers_for):
    resp = complete(client, headers_for(scene.teacher), scene.lesson.id)
    assert resp.status_code == 200

    assert status_of(session, scene.lesson.id) == LessonStatus.completed
    assert spent(session, scene.xiaoming.id) == -2.5
    assert spent(session, scene.xiaohong.id) == -2.5
    # 起始 10 课时，扣完还剩 7.5
    assert balance_of(session, scene.xiaoming.id) == 7.5


def test_扣的是小时数不是固定一节课(client, session, scene, headers_for):
    """2.5 小时的课就扣 2.5 —— 「课时就是小时数」，不存在两套换算。"""
    complete(client, headers_for(scene.teacher), scene.lesson.id)
    assert consume_rows(session, scene.lesson.id)[0].amount == -2.5


def test_不带items时全员默认出勤(client, session, scene, headers_for):
    complete(client, headers_for(scene.teacher), scene.lesson.id)

    rows = attendance_rows(session, scene.lesson.id)
    assert len(rows) == 2
    assert {row.status for row in rows} == {AttendanceStatus.present}


def test_不带上课内容不能完成(client, session, scene, headers_for):
    """★ 上课内容必填（用户 2026-10-05 定的）。

    以前 body 整个可省（「一键完成」），加了 content 之后这条路封了 ——
    老师必须写清楚这节课上到哪了。
    """
    resp = complete(client, headers_for(scene.teacher), scene.lesson.id, content=None)
    assert resp.status_code == 422

    assert status_of(session, scene.lesson.id) == LessonStatus.scheduled
    assert consume_rows(session, scene.lesson.id) == []


def test_上课内容只有空格也不行(client, session, scene, headers_for):
    resp = complete(client, headers_for(scene.teacher), scene.lesson.id, content="   ")
    assert resp.status_code == 400
    assert "上课内容" in resp.json()["detail"]
    assert status_of(session, scene.lesson.id) == LessonStatus.scheduled


def test_上课内容被存下来(client, session, scene, headers_for):
    complete(client, headers_for(scene.teacher), scene.lesson.id, content="  上到第 5 页  ")
    assert content_of(session, scene.lesson.id) == "上到第 5 页"  # strip 过


def test_提交的考勤状态被采纳(client, session, scene, headers_for):
    resp = complete(
        client,
        headers_for(scene.teacher),
        scene.lesson.id,
        [
            {"student_id": scene.xiaoming.id, "status": "present"},
            {"student_id": scene.xiaohong.id, "status": "leave"},
        ],
    )
    assert resp.status_code == 200

    by_student = {row.student_id: row.status for row in attendance_rows(session, scene.lesson.id)}
    assert by_student[scene.xiaoming.id] == AttendanceStatus.present
    assert by_student[scene.xiaohong.id] == AttendanceStatus.leave


def test_1对1请假缺勤都不扣课时(client, session, scene, headers_for):
    """★ 2026-10-05 用户改的口径。

    原来是「出勤/请假/缺勤都扣」，现在**1对1 只有出勤才扣** ——
    人没来这节课就没上，收钱没道理。

    （`scene` 的班是 `1对1`，见夹具。）
    """
    resp = complete(
        client,
        headers_for(scene.teacher),
        scene.lesson.id,
        [
            {"student_id": scene.xiaoming.id, "status": "absent"},
            {"student_id": scene.xiaohong.id, "status": "leave"},
        ],
    )
    assert resp.status_code == 200

    assert consume_rows(session, scene.lesson.id) == []
    assert spent(session, scene.xiaoming.id) == 0.0
    assert spent(session, scene.xiaohong.id) == 0.0

    # 考勤照记 —— 扣不扣课时和记不记考勤是两回事
    by_student = {r.student_id: r.status for r in attendance_rows(session, scene.lesson.id)}
    assert by_student[scene.xiaoming.id] == AttendanceStatus.absent
    assert by_student[scene.xiaohong.id] == AttendanceStatus.leave


def test_1对1只扣出勤的那个(client, session, scene, headers_for):
    """一个来了一个没来：只扣来的那个。"""
    complete(
        client,
        headers_for(scene.teacher),
        scene.lesson.id,
        [
            {"student_id": scene.xiaoming.id, "status": "present"},
            {"student_id": scene.xiaohong.id, "status": "leave"},
        ],
    )
    assert spent(session, scene.xiaoming.id) == -2.5
    assert spent(session, scene.xiaohong.id) == 0.0


def test_1对2也只扣出勤的那个(
    client, session, make_class, make_student, make_user, make_lesson, enroll, fund,
    headers_for,
):
    """★ 2026-10-07 用户改的口径：**1对2 跟 1对1 一样按出勤扣**。

    原话：「对于 1对1 和 1对2 的学生来说，他买多少课时就是多少，所以就是直接
    按照学生自己的课时来扣就好，上课了就扣课时，没上就不扣。」

    （`scene` 的班是 1对1，所以这里自己建一个 1对2 的。）
    """
    klass = make_class(name="YDE001", class_type="1对2")
    teacher = make_user("13900000021", role=Role.teacher)
    present = fund(make_student(name="来的"))
    leaver = fund(make_student(name="请假的"))
    absent = fund(make_student(name="没来的"))
    for student in (present, leaver, absent):
        enroll(klass, student)

    lesson = make_lesson(klass=klass, teacher=teacher, hours=1.5)
    resp = complete(
        client,
        headers_for(teacher),
        lesson.id,
        [
            {"student_id": present.id, "status": "present"},
            {"student_id": leaver.id, "status": "leave"},
            {"student_id": absent.id, "status": "absent"},
        ],
    )
    assert resp.status_code == 200

    assert spent(session, present.id) == -1.5
    assert spent(session, leaver.id) == 0.0
    assert spent(session, absent.id) == 0.0


def test_1对2全员没来就不扣(
    client, session, make_class, make_student, make_user, make_lesson, enroll, fund,
    headers_for,
):
    """1对2 全员请假/缺勤 = 这节课没上，谁都不扣，没课时也放行。"""
    klass = make_class(name="YDE002", class_type="1对2")
    teacher = make_user("13900000022", role=Role.teacher)
    one = make_student(name="甲")  # 故意不给课时
    two = make_student(name="乙")
    for student in (one, two):
        enroll(klass, student)

    lesson = make_lesson(klass=klass, teacher=teacher, hours=1.0)
    resp = complete(
        client,
        headers_for(teacher),
        lesson.id,
        [
            {"student_id": one.id, "status": "leave"},
            {"student_id": two.id, "status": "absent"},
        ],
    )
    assert resp.status_code == 200
    assert consume_rows(session, lesson.id) == []


def test_1对2出勤改成请假要退回课时(
    client, session, make_class, make_student, make_user, make_lesson, enroll, fund,
    headers_for,
):
    """事后改考勤的重算路径也要认 1对2 —— 只认 1对1 的话这里就漏收了。"""
    klass = make_class(name="YDE003", class_type="1对2")
    teacher = make_user("13900000023", role=Role.teacher)
    student = fund(make_student(name="先来了后来改成请假"))  # 默认 10 课时
    enroll(klass, student)

    lesson = make_lesson(klass=klass, teacher=teacher, hours=2.0)
    complete(
        client,
        headers_for(teacher),
        lesson.id,
        [{"student_id": student.id, "status": "present"}],
    )
    assert spent(session, student.id) == -2.0

    resp = set_attendance(
        client,
        headers_for(teacher),
        lesson.id,
        [{"student_id": student.id, "status": "leave"}],
    )
    assert resp.status_code == 200

    # ★ 流水被删（不是写一条 +2.0 的对冲），余额自己回升
    assert consume_rows(session, lesson.id) == []
    assert balance_of(session, student.id) == 10.0


def test_其他班型开课就扣全员(
    client, session, make_class, make_student, make_user, make_lesson, enroll, fund,
    headers_for,
):
    """★ 小班（和 1对2）跟 1对1 反过来：不管来没来，开课就扣全员。

    请假也占着时段和老师，小班照收 —— 这条**没变**。
    """
    klass = make_class(name="XB001", class_type="1对3")
    teacher = make_user("13900000031", role=Role.teacher)
    present = fund(make_student(name="来的"))
    leaver = fund(make_student(name="请假的"))
    absent = fund(make_student(name="没来的"))
    for student in (present, leaver, absent):
        enroll(klass, student)

    lesson = make_lesson(klass=klass, teacher=teacher, hours=1.0)
    resp = complete(
        client,
        headers_for(teacher),
        lesson.id,
        [
            {"student_id": present.id, "status": "present"},
            {"student_id": leaver.id, "status": "leave"},
            {"student_id": absent.id, "status": "absent"},
        ],
    )
    assert resp.status_code == 200

    for student in (present, leaver, absent):
        assert spent(session, student.id) == -1.0


def test_认不出的班型按其他班型算(
    client, session, make_class, make_student, make_user, make_lesson, enroll, fund,
    headers_for,
):
    """自定义类型不走 1对1 那条宽免 —— **宁可多收，不能漏收**。"""
    klass = make_class(name="VIP班", class_type="VIP")
    teacher = make_user("13900000032", role=Role.teacher)
    student = fund(make_student(name="VIP学生"))
    enroll(klass, student)

    lesson = make_lesson(klass=klass, teacher=teacher, hours=1.0)
    complete(
        client,
        headers_for(teacher),
        lesson.id,
        [{"student_id": student.id, "status": "leave"}],
    )
    assert spent(session, student.id) == -1.0


def test_消耗流水留下操作人(client, session, scene, headers_for):
    """家长问起来要能查到是谁点的。"""
    complete(client, headers_for(scene.teacher), scene.lesson.id)
    assert all(
        row.created_by == scene.teacher.id
        for row in consume_rows(session, scene.lesson.id)
    )


def test_完成两次第二次409且不再扣课时(client, session, scene, headers_for):
    """老师误点两次「完成上课」，或网络重试导致请求重发。"""
    headers = headers_for(scene.teacher)
    assert complete(client, headers, scene.lesson.id).status_code == 200

    resp = complete(client, headers, scene.lesson.id)
    assert resp.status_code == 409

    assert len(consume_rows(session, scene.lesson.id)) == 2
    assert spent(session, scene.xiaoming.id) == -2.5


def test_已取消的课不能完成(client, session, scene, headers_for):
    scene.lesson.status = LessonStatus.cancelled
    session.add(scene.lesson)
    session.commit()

    assert complete(client, headers_for(scene.teacher), scene.lesson.id).status_code == 409


def test_完成时带无效学生则一条都不写(client, session, scene, admin_headers):
    """全有或全无 —— 部分成功会让调用方不知道该不该重试，而重试会重复扣。"""
    resp = complete(
        client,
        admin_headers,
        scene.lesson.id,
        [
            {"student_id": scene.xiaoming.id, "status": "present"},
            {"student_id": 9999, "status": "present"},
        ],
    )
    assert resp.status_code == 400
    assert "9999" in resp.json()["detail"]

    assert consume_rows(session, scene.lesson.id) == []
    assert attendance_rows(session, scene.lesson.id) == []
    assert status_of(session, scene.lesson.id) == LessonStatus.scheduled


def test_课时不够整节课失败并列出是谁(client, session, scene, headers_for):
    """★ 2026-10-05 用户定的：**不**允许扣成负数，谁不够就整节课失败。

    课时是预交的学费，欠费了该让老师先收钱，而不是系统默默兜着。
    """
    # 小明的 10 课时花掉，只剩 0.5 —— 扣不动 2.5 的课
    session.add(
        HourTransaction(
            student_id=scene.xiaoming.id, type=TxnType.adjust, amount=-9.5,
            note="把钱花掉",
        )
    )
    session.commit()

    resp = complete(client, headers_for(scene.teacher), scene.lesson.id)
    assert resp.status_code == 400

    detail = resp.json()["detail"]
    assert "课时不足" in detail
    assert "小明" in detail          # 列出是谁
    assert "小红" not in detail      # 够的不要列进去

    # ★ 全有或全无：够的那个也一行没写
    assert consume_rows(session, scene.lesson.id) == []
    assert attendance_rows(session, scene.lesson.id) == []
    assert status_of(session, scene.lesson.id) == LessonStatus.scheduled
    assert balance_of(session, scene.xiaohong.id) == 10.0


def test_余额刚好等于课时可以扣(client, session, scene, headers_for):
    """边界：剩 2.5 扣 2.5 是允许的，扣完为 0 —— 判据是 `<`，不是 `<=`。"""
    session.add(
        HourTransaction(
            student_id=scene.xiaoming.id, type=TxnType.adjust, amount=-7.5,
            note="刚好花到 2.5",
        )
    )
    session.add(
        HourTransaction(
            student_id=scene.xiaohong.id, type=TxnType.adjust, amount=-7.5,
            note="刚好花到 2.5",
        )
    )
    session.commit()

    resp = complete(client, headers_for(scene.teacher), scene.lesson.id)
    assert resp.status_code == 200
    assert balance_of(session, scene.xiaoming.id) == 0.0


def test_1对1全员请假时没有课时也放行(client, session, scene, headers_for):
    """★ 不扣课时的课不该被余额拦下。

    1对1 全员请假 → 一分钱不扣 → 余额校验不该跑。
    不然「按 0 课时算的检查」会把一节根本不来人的课也卡住。
    """
    # 把两个人的课时全花光
    for student in (scene.xiaoming, scene.xiaohong):
        session.add(
            HourTransaction(
                student_id=student.id, type=TxnType.adjust, amount=-10,
                note="清空",
            )
        )
    session.commit()

    resp = complete(
        client, headers_for(scene.teacher), scene.lesson.id,
        [
            {"student_id": scene.xiaoming.id, "status": "leave"},
            {"student_id": scene.xiaohong.id, "status": "absent"},
        ],
    )
    assert resp.status_code == 200
    assert consume_rows(session, scene.lesson.id) == []


def test_负余额的学生被拦下来(client, session, scene, headers_for):
    """手工 adjust 退过费、余额已经是负的，照样过不了余额校验。"""
    session.add(
        HourTransaction(
            student_id=scene.xiaoming.id, type=TxnType.adjust, amount=-12,
            note="退费",
        )
    )
    session.commit()
    assert balance_of(session, scene.xiaoming.id) == -2.0

    resp = complete(client, headers_for(scene.teacher), scene.lesson.id)
    assert resp.status_code == 400
    assert "小明" in resp.json()["detail"]


def test_老师可以完成自己的课(client, scene, headers_for):
    assert complete(client, headers_for(scene.teacher), scene.lesson.id).status_code == 200


def test_老师不能完成别人的课(client, session, scene, headers_for, make_user):
    """★ 403 之外还要确认**真的没扣**，不能只是响应码对了。"""
    other = make_user("13900000022", role=Role.teacher)
    resp = complete(client, headers_for(other), scene.lesson.id)
    assert resp.status_code == 403

    assert status_of(session, scene.lesson.id) == LessonStatus.scheduled
    assert consume_rows(session, scene.lesson.id) == []


def test_未登录不能完成(client, scene):
    assert client.post(f"/api/lessons/{scene.lesson.id}/complete").status_code == 401


# ── ★ 在册日期边界 ─────────────────────────────────


def test_上课日之后才入班的学生不扣(
    client, session, scene, headers_for, make_student, enroll, fund
):
    latecomer = fund(make_student(name="后来的"))
    enroll(scene.klass, latecomer, joined_on=Date(2026, 10, 6))  # 课在 10-05

    complete(client, headers_for(scene.teacher), scene.lesson.id)

    assert spent(session, latecomer.id) == 0.0
    assert spent(session, scene.xiaoming.id) == -2.5


def test_上课当天入班的学生要扣(
    client, session, scene, headers_for, make_student, enroll, fund
):
    """边界包含当日：joined_on <= lesson_date。"""
    same_day = fund(make_student(name="当天来的"))
    enroll(scene.klass, same_day, joined_on=Date(2026, 10, 5))

    complete(client, headers_for(scene.teacher), scene.lesson.id)
    assert spent(session, same_day.id) == -2.5


def test_上课前就退班的学生不扣(
    client, session, scene, headers_for, make_student, enroll, fund
):
    """left_on <= lesson_date 算已经不在册了。"""
    leaver = fund(make_student(name="退班的"))
    enroll(scene.klass, leaver, joined_on=Date(2026, 9, 1), left_on=Date(2026, 10, 5))

    complete(client, headers_for(scene.teacher), scene.lesson.id)
    assert spent(session, leaver.id) == 0.0


def test_上完课才退班的学生要扣(
    client, session, scene, headers_for, make_student, enroll, fund
):
    """left_on > lesson_date 说明上课那天还在册。"""
    leaver = fund(make_student(name="上完才退的"))
    enroll(scene.klass, leaver, joined_on=Date(2026, 9, 1), left_on=Date(2026, 10, 6))

    complete(client, headers_for(scene.teacher), scene.lesson.id)
    assert spent(session, leaver.id) == -2.5


def test_学生可以同时被两个班各扣一次(
    session, client, make_class, make_student, make_user, make_lesson, enroll, fund,
    headers_for,
):
    """唯一索引是 (lesson_id, student_id)，跨课各扣各的。"""
    teacher = make_user("13900000024", role=Role.teacher)
    klass_a = make_class(name="YDY900", rate=80.0)
    klass_b = make_class(name="YDY901", rate=100.0)
    student = fund(make_student(name="两边跑"))
    enroll(klass_a, student)
    enroll(klass_b, student)

    lesson_a = make_lesson(klass=klass_a, teacher=teacher, hours=1.0)
    lesson_b = make_lesson(klass=klass_b, teacher=teacher, hours=2.0)

    headers = headers_for(teacher)
    complete(client, headers, lesson_a.id)
    complete(client, headers, lesson_b.id)

    assert spent(session, student.id) == -3.0


# ── ★ 取消 ────────────────────────────────────────


def test_取消已完成的课把课时退回去(client, session, scene, admin_headers, headers_for):
    complete(client, headers_for(scene.teacher), scene.lesson.id)
    assert balance_of(session, scene.xiaoming.id) == 7.5

    resp = client.post(
        f"/api/lessons/{scene.lesson.id}/cancel", headers=admin_headers
    )
    assert resp.status_code == 200

    assert balance_of(session, scene.xiaoming.id) == 10.0
    assert balance_of(session, scene.xiaohong.id) == 10.0
    assert consume_rows(session, scene.lesson.id) == []
    assert status_of(session, scene.lesson.id) == LessonStatus.cancelled


def test_取消后考勤记录仍然保留(client, session, scene, admin_headers, headers_for):
    """那是「本来安排了、后来取消了」的痕迹，删了就看不出原本要给谁上。"""
    complete(client, headers_for(scene.teacher), scene.lesson.id)
    client.post(f"/api/lessons/{scene.lesson.id}/cancel", headers=admin_headers)

    assert len(attendance_rows(session, scene.lesson.id)) == 2


def test_取消还没上过的课不产生任何流水(client, session, scene, admin_headers):
    resp = client.post(
        f"/api/lessons/{scene.lesson.id}/cancel", headers=admin_headers
    )
    assert resp.status_code == 200

    assert consume_rows(session, scene.lesson.id) == []
    assert status_of(session, scene.lesson.id) == LessonStatus.cancelled


def test_取消两次第二次409(client, session, scene, admin_headers):
    headers = admin_headers
    assert client.post(f"/api/lessons/{scene.lesson.id}/cancel", headers=headers).status_code == 200
    assert client.post(f"/api/lessons/{scene.lesson.id}/cancel", headers=headers).status_code == 409


def test_老师不能取消课程(client, session, scene, headers_for):
    resp = client.post(
        f"/api/lessons/{scene.lesson.id}/cancel", headers=headers_for(scene.teacher)
    )
    assert resp.status_code == 403


def test_取消后不能重新完成(client, scene, admin_headers, headers_for):
    client.post(f"/api/lessons/{scene.lesson.id}/cancel", headers=admin_headers)
    assert complete(client, headers_for(scene.teacher), scene.lesson.id).status_code == 409


# ── 事后改考勤 ─────────────────────────────────────


def test_已完成的课可以改考勤(client, session, scene, headers_for):
    headers = headers_for(scene.teacher)
    complete(client, headers, scene.lesson.id)

    resp = set_attendance(
        client, headers, scene.lesson.id,
        [{"student_id": scene.xiaoming.id, "status": "absent"}],
    )
    assert resp.status_code == 200

    by_student = {row.student_id: row.status for row in attendance_rows(session, scene.lesson.id)}
    assert by_student[scene.xiaoming.id] == AttendanceStatus.absent
    # 没提到的学生不动
    assert by_student[scene.xiaohong.id] == AttendanceStatus.present


def test_1对1把出勤改成请假要退回课时(client, session, scene, headers_for):
    """★ 2026-10-05 用户定的：**考勤一改，课时跟着重算**。

    老师点错了（把没来的人勾成出勤）再改正，课时必须退回去 ——
    不然就是静默多收学生的钱，账面上还看不出来。
    """
    headers = headers_for(scene.teacher)
    complete(client, headers, scene.lesson.id)
    assert spent(session, scene.xiaoming.id) == -2.5

    set_attendance(
        client, headers, scene.lesson.id,
        [{"student_id": scene.xiaoming.id, "status": "leave"}],
    )
    assert spent(session, scene.xiaoming.id) == 0.0
    assert balance_of(session, scene.xiaoming.id) == 10.0
    # 另一个学生没动，还扣着
    assert spent(session, scene.xiaohong.id) == -2.5


def test_改回出勤再扣一次(client, session, scene, headers_for):
    """来回改不能把课时越改越多 —— 只动差额，不重复扣。"""
    headers = headers_for(scene.teacher)
    complete(client, headers, scene.lesson.id)

    set_attendance(client, headers, scene.lesson.id,
                   [{"student_id": scene.xiaoming.id, "status": "leave"}])
    set_attendance(client, headers, scene.lesson.id,
                   [{"student_id": scene.xiaoming.id, "status": "present"}])

    assert spent(session, scene.xiaoming.id) == -2.5
    assert len([r for r in consume_rows(session, scene.lesson.id)
                if r.student_id == scene.xiaoming.id]) == 1


def test_其他班型改考勤不影响课时(
    client, session, make_class, make_student, make_user, make_lesson, enroll, fund,
    headers_for,
):
    """小班本来就全员扣，改成请假也不退 —— 口径没变。"""
    klass = make_class(name="XB002", class_type="1对3")
    teacher = make_user("13900000033", role=Role.teacher)
    student = fund(make_student(name="小班学生"))
    enroll(klass, student)
    lesson = make_lesson(klass=klass, teacher=teacher, hours=1.0)

    headers = headers_for(teacher)
    complete(client, headers, lesson.id, [{"student_id": student.id, "status": "present"}])
    set_attendance(client, headers, lesson.id,
                   [{"student_id": student.id, "status": "leave"}])

    assert spent(session, student.id) == -1.0


def test_改考勤时可以顺手改上课内容(client, session, scene, headers_for):
    headers = headers_for(scene.teacher)
    complete(client, headers, scene.lesson.id, content="原内容")

    resp = set_attendance(
        client, headers, scene.lesson.id,
        [{"student_id": scene.xiaoming.id, "status": "present"}],
        content="改过的内容",
    )
    assert resp.status_code == 200
    assert content_of(session, scene.lesson.id) == "改过的内容"


def test_补扣时课时不够要拦下来(client, session, scene, headers_for):
    """课后把请假改成出勤，但学生课时不够 —— 不能悄悄扣成负数。"""
    headers = headers_for(scene.teacher)
    # 先按「全员请假」完成，一分钱不扣
    complete(
        client, headers, scene.lesson.id,
        [
            {"student_id": scene.xiaoming.id, "status": "leave"},
            {"student_id": scene.xiaohong.id, "status": "leave"},
        ],
    )
    # 小明只剩 0.5，补扣 2.5 不够
    session.add(
        HourTransaction(
            student_id=scene.xiaoming.id, type=TxnType.adjust, amount=-9.5,
            note="把钱花掉",
        )
    )
    session.commit()

    resp = set_attendance(client, headers, scene.lesson.id,
                          [{"student_id": scene.xiaoming.id, "status": "present"}])
    assert resp.status_code == 400
    assert "课时不足" in resp.json()["detail"]
    assert spent(session, scene.xiaoming.id) == 0.0


def test_还没上课的课不能改考勤(client, scene, headers_for):
    resp = client.post(
        f"/api/lessons/{scene.lesson.id}/attendance",
        json={"items": [{"student_id": scene.xiaoming.id, "status": "leave"}]},
        headers=headers_for(scene.teacher),
    )
    assert resp.status_code == 409


def test_改考勤带无效学生则一条都不改(client, session, scene, headers_for):
    headers = headers_for(scene.teacher)
    complete(client, headers, scene.lesson.id)

    resp = client.post(
        f"/api/lessons/{scene.lesson.id}/attendance",
        json={
            "items": [
                {"student_id": scene.xiaoming.id, "status": "absent"},
                {"student_id": 9999, "status": "absent"},
            ]
        },
        headers=headers,
    )
    assert resp.status_code == 400

    by_student = {row.student_id: row.status for row in attendance_rows(session, scene.lesson.id)}
    assert by_student[scene.xiaoming.id] == AttendanceStatus.present


def test_老师不能改别人课的考勤(client, session, scene, headers_for, make_user):
    other = make_user("13900000025", role=Role.teacher)
    complete(client, headers_for(scene.teacher), scene.lesson.id)

    resp = client.post(
        f"/api/lessons/{scene.lesson.id}/attendance",
        json={"items": [{"student_id": scene.xiaoming.id, "status": "absent"}]},
        headers=headers_for(other),
    )
    assert resp.status_code == 403


def test_空items被拒绝(client, scene, headers_for):
    headers = headers_for(scene.teacher)
    complete(client, headers, scene.lesson.id)

    resp = client.post(
        f"/api/lessons/{scene.lesson.id}/attendance", json={"items": []}, headers=headers
    )
    assert resp.status_code == 400
