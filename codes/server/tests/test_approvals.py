"""审批：改期申请 / 撤回 / 通过 / 驳回（实施计划 5.7）。

老师提申请 → 管理员待办里通过或驳回，全程留痕。管理员自己改期仍走
`PATCH /lessons/{id}`（免审批），这里测的只是老师这一侧那条路。
"""

from datetime import date as Date

from sqlmodel import func, select

import pytest

from app.models import (
    Approval,
    ApprovalStatus,
    HourTransaction,
    Lesson,
    LessonStatus,
    Role,
)


def payload_for(**overrides) -> dict:
    payload = {
        "date": "2026-10-15",
        "start_time": "16:00",
        "reason": "家长要求调到周末",
    }
    payload.update(overrides)
    return payload


def approval_rows(session, status_of_rows=None) -> list[Approval]:
    statement = select(Approval)
    if status_of_rows is not None:
        statement = statement.where(Approval.status == status_of_rows)
    return list(session.exec(statement).all())


def approval_count(session) -> int:
    return session.exec(select(func.count()).select_from(Approval)).one()


def reschedule(client, lesson, teacher, headers_for, **overrides):
    """老师提一条改期申请，返回响应。"""
    return client.post(
        f"/api/lessons/{lesson.id}/reschedule",
        json=payload_for(**overrides),
        headers=headers_for(teacher),
    )


@pytest.fixture
def admin(make_user):
    return make_user("13900000020", role=Role.admin)


@pytest.fixture
def teacher(make_user):
    return make_user("13900000021", role=Role.teacher)


@pytest.fixture
def other_teacher(make_user):
    return make_user("13900000022", role=Role.teacher)


# ── 提申请 ────────────────────────────────────────


def test_提申请成功但不改动课程时间(client, teacher, make_lesson, headers_for, session):
    """★ 这一条是整轮的口径：**提申请的那一刻课程时间一动不动**。"""
    lesson = make_lesson(teacher=teacher)

    resp = reschedule(client, lesson, teacher, headers_for)
    assert resp.status_code == 201

    body = resp.json()
    # payload 摊平成真字段，前端不用自己 JSON.parse
    assert body["approval"]["new_date"] == "2026-10-15"
    assert body["approval"]["new_start_time"] == "16:00:00"
    assert body["approval"]["reason"] == "家长要求调到周末"
    assert body["approval"]["status"] == "pending"
    assert body["approval"]["requested_by_name"] == teacher.display_name

    # 课程本身：还是老时间
    assert body["lesson_date"] == "2026-10-05"
    assert body["start_time"] == "09:00:00"

    session.expire_all()
    row = session.exec(select(Lesson).where(Lesson.id == lesson.id)).one()
    assert row.lesson_date == Date(2026, 10, 5)


def test_提申请不产生任何课时流水(client, teacher, make_lesson, headers_for, session):
    """改期不是上课 —— 一条 consume 都不该写。"""
    lesson = make_lesson(teacher=teacher)
    reschedule(client, lesson, teacher, headers_for)

    assert session.exec(select(func.count()).select_from(HourTransaction)).one() == 0


def test_提申请时payload里的课名老师名都带出来(client, teacher, make_lesson, headers_for, make_class):
    """管理员在待办里要能一眼看出是哪节课，不用自己再查两次。"""
    klass = make_class(name="YDY007")
    lesson = make_lesson(klass=klass, teacher=teacher)

    body = reschedule(client, lesson, teacher, headers_for).json()
    assert body["approval"]["class_id"] == klass.id
    assert body["approval"]["class_name"] == "YDY007"
    assert body["approval"]["class_type"] == "1对1"
    assert body["approval"]["teacher_name"] == teacher.display_name
    assert body["approval"]["lesson_date"] == "2026-10-05"


def test_理由为空报400(client, teacher, make_lesson, headers_for):
    """「填了一串空格」也算空 —— 没有理由的申请只是盖章。"""
    lesson = make_lesson(teacher=teacher)
    resp = reschedule(client, lesson, teacher, headers_for, reason="   ")
    assert resp.status_code == 400
    assert "理由" in resp.json()["detail"]


def test_理由缺失报422(client, teacher, make_lesson, headers_for):
    lesson = make_lesson(teacher=teacher)
    resp = client.post(
        f"/api/lessons/{lesson.id}/reschedule",
        json={"date": "2026-10-15", "start_time": "16:00"},
        headers=headers_for(teacher),
    )
    assert resp.status_code == 422


def test_不能给别人的课提申请(client, teacher, other_teacher, make_lesson, headers_for):
    lesson = make_lesson(teacher=other_teacher)
    resp = reschedule(client, lesson, teacher, headers_for)
    assert resp.status_code == 403
    assert "自己的课程" in resp.json()["detail"]


def test_管理员不能提申请(client, admin, make_lesson, headers_for):
    """管理员自己改期直接 PATCH —— 让审批人给自己发申请没有意义。"""
    lesson = make_lesson(teacher=admin)
    resp = reschedule(client, lesson, admin, headers_for)
    assert resp.status_code == 403


def test_已完成的课不能提申请(client, teacher, make_lesson, headers_for):
    lesson = make_lesson(teacher=teacher, status=LessonStatus.completed)
    resp = reschedule(client, lesson, teacher, headers_for)
    assert resp.status_code == 409
    assert "已排课" in resp.json()["detail"]


def test_已取消的课不能提申请(client, teacher, make_lesson, headers_for):
    lesson = make_lesson(teacher=teacher, status=LessonStatus.cancelled)
    assert reschedule(client, lesson, teacher, headers_for).status_code == 409


def test_同一节课不能提两条待审批(client, teacher, make_lesson, headers_for):
    lesson = make_lesson(teacher=teacher)
    assert reschedule(client, lesson, teacher, headers_for).status_code == 201
    resp = reschedule(client, lesson, teacher, headers_for)

    assert resp.status_code == 400
    assert "撤回" in resp.json()["detail"]


def test_未登录不能提申请(client, teacher, make_lesson):
    lesson = make_lesson(teacher=teacher)
    assert (
        client.post(f"/api/lessons/{lesson.id}/reschedule", json=payload_for()).status_code
        == 401
    )


# ── 列表 ──────────────────────────────────────────


def test_管理员默认只看到待审批(client, admin, teacher, make_lesson, headers_for):
    lesson = make_lesson(teacher=teacher)
    reschedule(client, lesson, teacher, headers_for)

    resp = client.get("/api/approvals", headers=headers_for(admin))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["status"] == "pending"
    assert body[0]["target_id"] == lesson.id
    assert body[0]["requested_by_name"] == teacher.display_name


def test_已处理的不出现在默认列表里(client, admin, teacher, make_lesson, headers_for):
    lesson = make_lesson(teacher=teacher)
    reschedule(client, lesson, teacher, headers_for)

    approval_id = pending_id(client, admin, headers_for)
    client.post(
        f"/api/approvals/{approval_id}/reject", json={}, headers=headers_for(admin)
    )

    assert client.get("/api/approvals", headers=headers_for(admin)).json() == []
    history = client.get(
        "/api/approvals", params={"status": "rejected"}, headers=headers_for(admin)
    ).json()
    assert len(history) == 1


def test_老师不能看审批列表(client, teacher, headers_for):
    assert client.get("/api/approvals", headers=headers_for(teacher)).status_code == 403


def test_审批状态非法报422(client, admin, headers_for):
    resp = client.get(
        "/api/approvals", params={"status": "xxx"}, headers=headers_for(admin)
    )
    assert resp.status_code == 422


def test_待审批列表按提交先后排序(
    client, admin, teacher, make_lesson, headers_for, make_class
):
    """老的排前面 —— 那是管理员该先处理的那条。"""
    klass = make_class()  # 两节课共用一个班：班级名是唯一的，建两个班名字会撞
    first = make_lesson(klass=klass, teacher=teacher)
    second = make_lesson(klass=klass, teacher=teacher)
    reschedule(client, first, teacher, headers_for)
    reschedule(client, second, teacher, headers_for)

    body = client.get("/api/approvals", headers=headers_for(admin)).json()
    assert [row["target_id"] for row in body] == [first.id, second.id]


def test_未登录不能看审批列表(client):
    assert client.get("/api/approvals").status_code == 401


# ── 通过 ──────────────────────────────────────────


def pending_id(client, admin, headers_for) -> int:
    return client.get("/api/approvals", headers=headers_for(admin)).json()[0]["id"]


def test_通过后课程时间真的改了(client, admin, teacher, make_lesson, headers_for, session):
    lesson = make_lesson(teacher=teacher)
    reschedule(client, lesson, teacher, headers_for)

    resp = client.post(
        f"/api/approvals/{pending_id(client, admin, headers_for)}/approve",
        headers=headers_for(admin),
    )
    assert resp.status_code == 200

    body = resp.json()
    assert body["status"] == "approved"
    assert body["reviewed_by"] == admin.id
    assert body["reviewed_by_name"] == admin.display_name
    assert body["reviewed_at"] is not None

    session.expire_all()
    row = session.exec(select(Lesson).where(Lesson.id == lesson.id)).one()
    assert row.lesson_date == Date(2026, 10, 15)
    assert row.start_time.hour == 16
    assert row.updated_at is not None


def test_通过后详情里能看到这条审批(client, admin, teacher, make_lesson, headers_for):
    lesson = make_lesson(teacher=teacher)
    reschedule(client, lesson, teacher, headers_for)
    client.post(
        f"/api/approvals/{pending_id(client, admin, headers_for)}/approve",
        headers=headers_for(admin),
    )

    body = client.get(f"/api/lessons/{lesson.id}", headers=headers_for(teacher)).json()
    assert body["approval"]["status"] == "approved"
    assert body["approval"]["new_date"] == "2026-10-15"
    assert body["lesson_date"] == "2026-10-15"


def test_重复通过报409(client, admin, teacher, make_lesson, headers_for):
    lesson = make_lesson(teacher=teacher)
    reschedule(client, lesson, teacher, headers_for)
    approval_id = pending_id(client, admin, headers_for)

    url = f"/api/approvals/{approval_id}/approve"
    assert client.post(url, headers=headers_for(admin)).status_code == 200
    resp = client.post(url, headers=headers_for(admin))

    assert resp.status_code == 409
    assert "已处理" in resp.json()["detail"]


def test_已驳回的不能再通过(client, admin, teacher, make_lesson, headers_for):
    lesson = make_lesson(teacher=teacher)
    reschedule(client, lesson, teacher, headers_for)
    approval_id = pending_id(client, admin, headers_for)

    client.post(
        f"/api/approvals/{approval_id}/reject", json={}, headers=headers_for(admin)
    )
    assert (
        client.post(
            f"/api/approvals/{approval_id}/approve", headers=headers_for(admin)
        ).status_code
        == 409
    )


def test_通过之前课程被完成会报409(client, admin, teacher, make_lesson, headers_for, session):
    """★ 本轮最要紧的一条守卫。

    申请挂着的期间老师把这节课上了（或管理员取消了），再点通过就会把一节
    **已经扣过课时、工资表上已有记录**的课改到别的日期上。必须 409。
    """
    lesson = make_lesson(teacher=teacher)
    reschedule(client, lesson, teacher, headers_for)
    approval_id = pending_id(client, admin, headers_for)

    # 模拟「这期间课上完了」
    session.expire_all()
    row = session.exec(select(Lesson).where(Lesson.id == lesson.id)).one()
    row.status = LessonStatus.completed
    session.add(row)
    session.commit()

    resp = client.post(
        f"/api/approvals/{approval_id}/approve", headers=headers_for(admin)
    )
    assert resp.status_code == 409
    assert "已排课" in resp.json()["detail"]

    # 课的时间没被改掉
    session.expire_all()
    fresh = session.exec(select(Lesson).where(Lesson.id == lesson.id)).one()
    assert fresh.lesson_date == Date(2026, 10, 5)
    # 而且申请还挂着 pending —— 管理员得自己去驳回
    assert (
        session.exec(select(Approval.status).where(Approval.id == approval_id)).one()
        == ApprovalStatus.pending
    )


def test_老师不能通过(client, teacher, make_lesson, headers_for):
    lesson = make_lesson(teacher=teacher)
    reschedule(client, lesson, teacher, headers_for)
    assert (
        client.post("/api/approvals/1/approve", headers=headers_for(teacher)).status_code
        == 403
    )


def test_通过不存在的审批报404(client, admin, headers_for):
    assert (
        client.post(
            "/api/approvals/9999/approve", headers=headers_for(admin)
        ).status_code
        == 404
    )


# ── 驳回 ──────────────────────────────────────────


def test_驳回不填理由也行(client, admin, teacher, make_lesson, headers_for):
    lesson = make_lesson(teacher=teacher)
    reschedule(client, lesson, teacher, headers_for)

    resp = client.post(
        f"/api/approvals/{pending_id(client, admin, headers_for)}/reject",
        json={},
        headers=headers_for(admin),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
    assert resp.json()["reject_reason"] is None


def test_驳回可以整个不发请求体(client, admin, teacher, make_lesson, headers_for):
    """`payload` 是 Optional —— 前端最省事的调法不该 422。"""
    lesson = make_lesson(teacher=teacher)
    reschedule(client, lesson, teacher, headers_for)
    resp = client.post(
        f"/api/approvals/{pending_id(client, admin, headers_for)}/reject",
        headers=headers_for(admin),
    )
    assert resp.status_code == 200


def test_驳回理由会记下来(client, admin, teacher, make_lesson, headers_for):
    lesson = make_lesson(teacher=teacher)
    reschedule(client, lesson, teacher, headers_for)

    resp = client.post(
        f"/api/approvals/{pending_id(client, admin, headers_for)}/reject",
        json={"reason": " 那天有公开课，挪到周四  "},
        headers=headers_for(admin),
    )
    assert resp.json()["reject_reason"] == "那天有公开课，挪到周四"


def test_驳回后课程时间一动不动(client, admin, teacher, make_lesson, headers_for, session):
    lesson = make_lesson(teacher=teacher)
    reschedule(client, lesson, teacher, headers_for)
    client.post(
        f"/api/approvals/{pending_id(client, admin, headers_for)}/reject",
        json={},
        headers=headers_for(admin),
    )

    session.expire_all()
    row = session.exec(select(Lesson).where(Lesson.id == lesson.id)).one()
    assert row.lesson_date == Date(2026, 10, 5)
    assert row.start_time.hour == 9


def test_重复驳回报409(client, admin, teacher, make_lesson, headers_for):
    lesson = make_lesson(teacher=teacher)
    reschedule(client, lesson, teacher, headers_for)
    approval_id = pending_id(client, admin, headers_for)

    url = f"/api/approvals/{approval_id}/reject"
    assert client.post(url, json={}, headers=headers_for(admin)).status_code == 200
    assert client.post(url, json={}, headers=headers_for(admin)).status_code == 409


def test_老师不能驳回(client, teacher, make_lesson, headers_for):
    lesson = make_lesson(teacher=teacher)
    reschedule(client, lesson, teacher, headers_for)
    assert (
        client.post(
            "/api/approvals/1/reject", json={}, headers=headers_for(teacher)
        ).status_code
        == 403
    )


def test_驳回后可以重新提交(client, admin, teacher, make_lesson, headers_for, session):
    lesson = make_lesson(teacher=teacher)
    reschedule(client, lesson, teacher, headers_for)
    client.post(
        f"/api/approvals/{pending_id(client, admin, headers_for)}/reject",
        json={},
        headers=headers_for(admin),
    )

    resp = reschedule(client, lesson, teacher, headers_for, reason="改到周五")
    assert resp.status_code == 201
    assert resp.json()["approval"]["reason"] == "改到周五"
    # 旧那条留痕
    assert approval_count(session) == 2
    assert len(approval_rows(session, ApprovalStatus.rejected)) == 1


# ── 撤回 ──────────────────────────────────────────


def test_撤回自己的申请(client, teacher, make_lesson, headers_for, session):
    lesson = make_lesson(teacher=teacher)
    reschedule(client, lesson, teacher, headers_for)
    approval_id = approval_rows(session)[0].id

    resp = client.post(
        f"/api/approvals/{approval_id}/withdraw", headers=headers_for(teacher)
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "withdrawn"


def test_撤回后不在待办列表里(client, admin, teacher, make_lesson, headers_for, session):
    lesson = make_lesson(teacher=teacher)
    reschedule(client, lesson, teacher, headers_for)
    approval_id = approval_rows(session)[0].id
    client.post(
        f"/api/approvals/{approval_id}/withdraw", headers=headers_for(teacher)
    )

    assert client.get("/api/approvals", headers=headers_for(admin)).json() == []


def test_撤回后详情里的审批行还在(client, teacher, make_lesson, headers_for, session):
    """撤回不是删除 —— 管理员要能看出「这节课本来想改，后来撤了」。"""
    lesson = make_lesson(teacher=teacher)
    reschedule(client, lesson, teacher, headers_for)
    approval_id = approval_rows(session)[0].id
    client.post(
        f"/api/approvals/{approval_id}/withdraw", headers=headers_for(teacher)
    )

    body = client.get(f"/api/lessons/{lesson.id}", headers=headers_for(teacher)).json()
    assert body["approval"]["status"] == "withdrawn"


def test_撤回后能重新提交且旧行仍是已撤回(
    client, teacher, make_lesson, headers_for, session
):
    lesson = make_lesson(teacher=teacher)
    reschedule(client, lesson, teacher, headers_for)
    approval_id = approval_rows(session)[0].id
    client.post(
        f"/api/approvals/{approval_id}/withdraw", headers=headers_for(teacher)
    )

    assert reschedule(client, lesson, teacher, headers_for).status_code == 201
    assert approval_count(session) == 2
    assert (
        session.exec(select(Approval.status).where(Approval.id == approval_id)).one()
        == ApprovalStatus.withdrawn
    )


def test_不能撤回别人的申请(
    client, teacher, other_teacher, make_lesson, headers_for, session
):
    lesson = make_lesson(teacher=other_teacher)
    reschedule(client, lesson, other_teacher, headers_for)
    approval_id = approval_rows(session)[0].id

    resp = client.post(
        f"/api/approvals/{approval_id}/withdraw", headers=headers_for(teacher)
    )
    assert resp.status_code == 403
    assert "自己" in resp.json()["detail"]


def test_管理员不能撤回(client, admin, teacher, make_lesson, headers_for, session):
    """管理员没有申请要撤（提不了），走不到这条路上。"""
    lesson = make_lesson(teacher=teacher)
    reschedule(client, lesson, teacher, headers_for)
    approval_id = approval_rows(session)[0].id

    assert (
        client.post(
            f"/api/approvals/{approval_id}/withdraw", headers=headers_for(admin)
        ).status_code
        == 403
    )


def test_已通过的不能撤回(client, admin, teacher, make_lesson, headers_for, session):
    lesson = make_lesson(teacher=teacher)
    reschedule(client, lesson, teacher, headers_for)
    approval_id = pending_id(client, admin, headers_for)
    client.post(
        f"/api/approvals/{approval_id}/approve", headers=headers_for(admin)
    )

    assert (
        client.post(
            f"/api/approvals/{approval_id}/withdraw", headers=headers_for(teacher)
        ).status_code
        == 409
    )


def test_撤回不存在的审批报404(client, teacher, headers_for):
    assert (
        client.post(
            "/api/approvals/9999/withdraw", headers=headers_for(teacher)
        ).status_code
        == 404
    )


# ── 详情里的 approval 字段 ─────────────────────────


def test_没有审批时详情里是null(client, teacher, make_lesson, headers_for):
    lesson = make_lesson(teacher=teacher)
    body = client.get(f"/api/lessons/{lesson.id}", headers=headers_for(teacher)).json()
    assert body["approval"] is None


def test_有两条时带出最近的一条(client, admin, teacher, make_lesson, headers_for, session):
    """按 **id desc** 取，不是按时间戳 —— 同一秒提交的两条也得分得出先后。"""
    lesson = make_lesson(teacher=teacher)
    reschedule(client, lesson, teacher, headers_for, reason="第一次")
    client.post(
        f"/api/approvals/{pending_id(client, admin, headers_for)}/reject",
        json={},
        headers=headers_for(admin),
    )
    reschedule(client, lesson, teacher, headers_for, reason="第二次")

    body = client.get(f"/api/lessons/{lesson.id}", headers=headers_for(teacher)).json()
    assert body["approval"]["reason"] == "第二次"
    assert body["approval"]["status"] == "pending"


# ── ★ 删除护栏 ────────────────────────────────────


def test_删掉带申请的课会一并清掉审批行(
    client, admin, teacher, make_lesson, headers_for, session
):
    """★ `approvals.target_id` 不是外键，SQLite 还会**复用**被删掉的 rowid。

    不清掉的话，下一节新建的课正好捡到同一个 id，管理员在待办里对着一节
    毫不相干的课点「通过」，把它的时间改掉 —— 而且没人看得出来。
    """
    lesson = make_lesson(teacher=teacher)
    reschedule(client, lesson, teacher, headers_for)
    assert approval_count(session) == 1

    assert (
        client.delete(f"/api/lessons/{lesson.id}", headers=headers_for(admin)).status_code
        == 200
    )
    assert approval_count(session) == 0


def test_取消课程刻意不清审批行(client, admin, teacher, make_lesson, headers_for, session):
    """⚠️ 相反的一条：完成 / 取消**故意不清**。

    用户要的正是「课后被完成了再点通过 → 409」那几个守卫，
    那行必须在。管理员靠**驳回**把它清掉。
    """
    lesson = make_lesson(teacher=teacher)
    reschedule(client, lesson, teacher, headers_for)

    assert (
        client.post(
            f"/api/lessons/{lesson.id}/cancel", headers=headers_for(admin)
        ).status_code
        == 200
    )
    assert approval_count(session) == 1


# ── 我的申请（2026-10-29 加回来）─────────────────────


def test_我的申请能看到全部历史(client, admin, teacher, make_lesson, headers_for):
    """★ 用户 2026-10-29 报的：提交两次后，第一次（撤回的）在**课程详情页**消失了。

    详情页只带最近一条（`latest_for_lesson`），所以这里给一个列全部的地方。
    三种状态都得在，且新的在前。
    """
    lesson = make_lesson(teacher=teacher)

    # 第一条：提了又撤回
    created = reschedule(client, lesson, teacher, headers_for).json()["approval"]
    client.post(
        f"/api/approvals/{created['id']}/withdraw", headers=headers_for(teacher)
    )

    # 第二条：提了被驳回
    reschedule(client, lesson, teacher, headers_for, reason="第二条")
    client.post(
        f"/api/approvals/{pending_id(client, admin, headers_for)}/reject",
        json={"reason": "那天有考试"},
        headers=headers_for(admin),
    )

    # 第三条：挂着待审批
    reschedule(client, lesson, teacher, headers_for, reason="第三条")

    body = client.get("/api/approvals/my", headers=headers_for(teacher)).json()
    assert [row["status"] for row in body] == ["pending", "rejected", "withdrawn"]
    # 新的在前（按 id desc），理由也跟着对上
    assert [row["reason"] for row in body] == ["第三条", "第二条", "家长要求调到周末"]
    assert body[1]["reject_reason"] == "那天有考试"
    # 带出课程信息（默认班名 YDY001），页面上不用再去查课
    assert body[0]["class_name"] == "YDY001"
    assert body[0]["lesson_date"] == "2026-10-05"


def test_我的申请只列自己的(client, teacher, other_teacher, make_lesson, headers_for):
    lesson = make_lesson(teacher=teacher)
    reschedule(client, lesson, teacher, headers_for)

    body = client.get("/api/approvals/my", headers=headers_for(other_teacher)).json()
    assert body == []


def test_我的申请管理员是空列表(client, admin, headers_for):
    """管理员提不了申请（`require_role(teacher)`），所以那儿本来就是空的。

    不额外 403 —— 前端不用为「这个入口管理员能不能点」再分一次叉。
    """
    assert client.get("/api/approvals/my", headers=headers_for(admin)).json() == []


def test_未登录不能看我的申请(client):
    assert client.get("/api/approvals/my").status_code == 401
