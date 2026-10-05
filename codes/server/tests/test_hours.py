"""课时流水的测试 —— 涉及钱，护栏最多。

重点是：不许手工录 `consume`、批量「全有或全无」、余额可以为负。
"""

from sqlalchemy import func
from sqlmodel import select

from app.models import HourTransaction, Role, TxnType


def _balance(session, student_id: int) -> float:
    """与 tests/test_safety_nets.py 的 balance_of 同口径。"""
    session.expire_all()
    return session.exec(
        select(func.coalesce(func.sum(HourTransaction.amount), 0.0)).where(
            HourTransaction.student_id == student_id
        )
    ).one()


def _txn_rows(session):
    session.expire_all()
    return list(session.exec(select(HourTransaction)))


# ── 单笔充值 ──────────────────────────────────────


def test_充值写正数流水并留created_by(
    client, session, make_user, headers_for, make_student
):
    admin = make_user("13900000001", role=Role.admin)
    student = make_student(name="张三")

    response = client.post(
        f"/api/students/{student.id}/hours",
        json={"type": "purchase", "amount": 10, "note": "买10课时"},
        headers=headers_for(admin),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["amount"] == 10
    assert body["type"] == "purchase"
    assert body["created_by"] == admin.id  # ★ 谁充的必须留痕
    assert body["lesson_id"] is None  # 手工流水不是因课消耗
    assert _balance(session, student.id) == 10


def test_充值金额必须为正(client, admin_headers, make_student):
    student = make_student(name="张三")
    response = client.post(
        f"/api/students/{student.id}/hours",
        json={"type": "purchase", "amount": 0},
        headers=admin_headers,
    )
    assert response.status_code == 400


def test_充值金额不能为负(client, session, admin_headers, make_student):
    student = make_student(name="张三")
    response = client.post(
        f"/api/students/{student.id}/hours",
        json={"type": "purchase", "amount": -5},
        headers=admin_headers,
    )
    assert response.status_code == 400
    assert _txn_rows(session) == []


# ── 调整 ──────────────────────────────────────────


def test_调整可以为负(client, session, admin_headers, make_student):
    student = make_student(name="张三")
    client.post(
        f"/api/students/{student.id}/hours",
        json={"type": "purchase", "amount": 10},
        headers=admin_headers,
    )

    response = client.post(
        f"/api/students/{student.id}/hours",
        json={"type": "adjust", "amount": -3, "note": "上月多扣了"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    assert _balance(session, student.id) == 7


def test_调整必须填备注(client, session, admin_headers, make_student):
    student = make_student(name="张三")
    response = client.post(
        f"/api/students/{student.id}/hours",
        json={"type": "adjust", "amount": -3},
        headers=admin_headers,
    )
    assert response.status_code == 400
    assert "备注" in response.json()["detail"]
    assert _txn_rows(session) == []


def test_调整只填空格也算没填(client, admin_headers, make_student):
    student = make_student(name="张三")
    response = client.post(
        f"/api/students/{student.id}/hours",
        json={"type": "adjust", "amount": -3, "note": "   "},
        headers=admin_headers,
    )
    assert response.status_code == 400


def test_调整金额不能为0(client, admin_headers, make_student):
    student = make_student(name="张三")
    response = client.post(
        f"/api/students/{student.id}/hours",
        json={"type": "adjust", "amount": 0, "note": "手滑"},
        headers=admin_headers,
    )
    assert response.status_code == 400


def test_余额可以为负(client, session, admin_headers, make_student):
    """`adjust` 就是用来修正错账和退费的，负余额是合法账实 —— 后端不设地板。"""
    student = make_student(name="张三")
    client.post(
        f"/api/students/{student.id}/hours",
        json={"type": "purchase", "amount": 5},
        headers=admin_headers,
    )
    response = client.post(
        f"/api/students/{student.id}/hours",
        json={"type": "adjust", "amount": -12, "note": "退费"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    assert _balance(session, student.id) == -7


# ── consume 必须被挡住 ────────────────────────────


def test_不允许手工录入consume流水(client, session, admin_headers, make_student):
    """★ 消耗流水只能由「完成上课」产生。

    手工入口要是放进来，`uq_consume_once` 那道防重复扣课时的安全网就形同虚设 ——
    而且这里产生的流水 lesson_id 是 None，索引根本不拦。
    """
    student = make_student(name="张三")
    response = client.post(
        f"/api/students/{student.id}/hours",
        json={"type": "consume", "amount": -1, "note": "想偷偷扣"},
        headers=admin_headers,
    )
    assert response.status_code == 400
    assert "消耗" in response.json()["detail"]
    assert _txn_rows(session) == []


def test_本轮的接口一条consume流水都产生不出来(
    client, session, admin_headers, make_student, make_class
):
    """把所有手工入口都走一遍，确认库里没有 consume。

    这是 `uq_consume_once` 的前提：本轮根本不该有 consume 行。
    """
    student = make_student(name="张三")
    klass = make_class(name="YDY001")

    client.post(
        f"/api/students/{student.id}/hours",
        json={"type": "purchase", "amount": 10},
        headers=admin_headers,
    )
    client.post(
        f"/api/students/{student.id}/hours",
        json={"type": "adjust", "amount": -1, "note": "调整"},
        headers=admin_headers,
    )
    client.post(
        "/api/students/hours/batch",
        json={"student_ids": [student.id], "amount": 5},
        headers=admin_headers,
    )
    client.post(
        f"/api/classes/{klass.id}/students",
        json={"student_ids": [student.id], "joined_on": "2026-01-01"},
        headers=admin_headers,
    )

    assert [t.type for t in _txn_rows(session)] == [
        TxnType.purchase,
        TxnType.adjust,
        TxnType.purchase,
    ]


# ── 流水明细 ──────────────────────────────────────


def test_流水明细带当前余额且新的在前(
    client, admin_headers, make_student
):
    student = make_student(name="张三")
    client.post(
        f"/api/students/{student.id}/hours",
        json={"type": "purchase", "amount": 10, "note": "第一笔"},
        headers=admin_headers,
    )
    client.post(
        f"/api/students/{student.id}/hours",
        json={"type": "adjust", "amount": -3, "note": "第二笔"},
        headers=admin_headers,
    )

    response = client.get(f"/api/students/{student.id}/hours", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["remaining_hours"] == 7
    assert len(body["transactions"]) == 2
    assert body["transactions"][0]["note"] == "第二笔"  # ★ 新的在前


def test_流水明细_没有流水时是空列表(client, admin_headers, make_student):
    student = make_student(name="张三")
    response = client.get(f"/api/students/{student.id}/hours", headers=admin_headers)
    assert response.json() == {"remaining_hours": 0, "transactions": []}


def test_老师能看流水但不能充(client, teacher_headers, make_student):
    student = make_student(name="张三")
    assert (
        client.get(f"/api/students/{student.id}/hours", headers=teacher_headers).status_code
        == 200
    )
    response = client.post(
        f"/api/students/{student.id}/hours",
        json={"type": "purchase", "amount": 10},
        headers=teacher_headers,
    )
    assert response.status_code == 403


# ── 批量充值 ──────────────────────────────────────


def test_批量充值给多个学生加课时(
    client, session, admin_headers, make_student
):
    a = make_student(name="张三")
    b = make_student(name="李四")

    response = client.post(
        "/api/students/hours/batch",
        json={"student_ids": [a.id, b.id], "amount": 12, "note": "整班买课时"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    assert len(response.json()) == 2
    assert _balance(session, a.id) == 12
    assert _balance(session, b.id) == 12


def test_批量充值含无效学生则一条都不写(
    client, session, admin_headers, make_student
):
    """★ 全有或全无。

    部分成功的话调用方不知道该不该重试，而重试会给已经充过的学生**重复充值**。
    """
    good = make_student(name="张三")

    response = client.post(
        "/api/students/hours/batch",
        json={"student_ids": [good.id, 99999], "amount": 12},
        headers=admin_headers,
    )
    assert response.status_code == 400
    assert _txn_rows(session) == []
    assert _balance(session, good.id) == 0


def test_批量充值_空列表返回400(client, admin_headers):
    response = client.post(
        "/api/students/hours/batch",
        json={"student_ids": [], "amount": 12},
        headers=admin_headers,
    )
    assert response.status_code == 400


def test_批量充值金额必须为正(client, session, admin_headers, make_student):
    student = make_student(name="张三")
    response = client.post(
        "/api/students/hours/batch",
        json={"student_ids": [student.id], "amount": -5},
        headers=admin_headers,
    )
    assert response.status_code == 400
    assert _txn_rows(session) == []


def test_批量充值不能给停用的学生充(client, session, admin_headers, make_student):
    student = make_student(name="张三", is_active=False)
    response = client.post(
        "/api/students/hours/batch",
        json={"student_ids": [student.id], "amount": 12},
        headers=admin_headers,
    )
    assert response.status_code == 400
    assert _txn_rows(session) == []


def test_批量充值同一个学生传两次只充一次(
    client, session, admin_headers, make_student
):
    student = make_student(name="张三")
    response = client.post(
        "/api/students/hours/batch",
        json={"student_ids": [student.id, student.id], "amount": 12},
        headers=admin_headers,
    )
    assert response.status_code == 201
    assert len(response.json()) == 1
    assert _balance(session, student.id) == 12  # 不是 24


def test_批量充值的路由没有被学生id挡住(client, admin_headers, make_student):
    """回归：`/students/hours/batch` 必须声明在 `/{student_id}/hours` 之前。

    顺序写反的话 `student_id: int` 匹配不上 "hours"，FastAPI 直接回 422。
    """
    student = make_student(name="张三")
    response = client.post(
        "/api/students/hours/batch",
        json={"student_ids": [student.id], "amount": 1},
        headers=admin_headers,
    )
    assert response.status_code == 201


def test_学生不存在时充值返回404(client, admin_headers):
    response = client.post(
        "/api/students/999/hours",
        json={"type": "purchase", "amount": 10},
        headers=admin_headers,
    )
    assert response.status_code == 404
