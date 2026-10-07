"""学生接口的测试 —— 重点是余额口径和「没有流水的学生也要显示 0」。"""

from datetime import date

from sqlmodel import func, select

from app.models import ClassStudent, HourTransaction, Student, TxnType


def _add_txn(session, student_id: int, amount: float, txn_type=TxnType.purchase):
    session.add(
        HourTransaction(
            student_id=student_id, type=txn_type, amount=amount, note="测试流水"
        )
    )
    session.commit()


# ── 建学生 ────────────────────────────────────────


def test_建学生(client, admin_headers):
    response = client.post(
        "/api/students",
        json={"name": "张三", "gender": "男", "phone": "13800001111"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "张三"
    assert body["is_active"] is True
    assert body["is_adult"] is None  # 没填就是未知


def test_建学生_默认送48课时(client, session, admin_headers):
    """★ 2026-10-05 用户定的：新生建档直接给 48 课时，省掉一次充值操作。

    ⚠️ 必须是**真写一条 purchase 流水**，不是给余额塞初值 ——
       余额是流水求和算出来的，塞初值的话学生详情页的流水里会凭空少一笔，
       而且这 48 课时说不清是谁什么时候给的。
    """
    response = client.post("/api/students", json={"name": "张三"}, headers=admin_headers)
    assert response.status_code == 201
    student_id = response.json()["id"]

    detail = client.get(f"/api/students/{student_id}", headers=admin_headers).json()
    assert detail["remaining_hours"] == 48

    txns = detail["transactions"]
    assert len(txns) == 1
    assert txns[0]["type"] == "purchase"
    assert txns[0]["amount"] == 48
    assert "新生" in txns[0]["note"]


def test_建学生_默认课时记在操作人名下(client, admin_headers):
    """家长问「这 48 课时谁给的」要查得到。"""
    response = client.post("/api/students", json={"name": "李四"}, headers=admin_headers)
    student_id = response.json()["id"]

    txn = client.get(f"/api/students/{student_id}", headers=admin_headers).json()[
        "transactions"
    ][0]
    assert txn["created_by"] is not None


def test_建学生_姓名必填(client, admin_headers):
    response = client.post("/api/students", json={"name": "   "}, headers=admin_headers)
    assert response.status_code == 400


def test_建学生_姓名不合法时不要送出课时(client, session, admin_headers):
    """★ 校验在写任何一行**之前** —— 400 之后库里不能留半截数据。

    这条曾经有真实风险：`flush()` 已经拿到了 student.id，如果姓名校验放在
    流水之后，就会留下一个「有 48 课时但没建成功」的孤儿学生。
    """
    before = session.exec(select(func.count()).select_from(Student)).one()
    before_txn = session.exec(
        select(func.count()).select_from(HourTransaction)
    ).one()

    resp = client.post("/api/students", json={"name": "  "}, headers=admin_headers)
    assert resp.status_code == 400

    session.expire_all()
    assert session.exec(select(func.count()).select_from(Student)).one() == before
    assert (
        session.exec(select(func.count()).select_from(HourTransaction)).one()
        == before_txn
    )


def test_建学生_性别只能是男女或留空(client, admin_headers):
    """DB 层有 CHECK，但这里要给出中文 400 而不是让 IntegrityError 变成 500。"""
    response = client.post(
        "/api/students", json={"name": "张三", "gender": "男性"}, headers=admin_headers
    )
    assert response.status_code == 400
    assert "性别" in response.json()["detail"]


def test_建学生_老师返回403(client, teacher_headers):
    response = client.post(
        "/api/students", json={"name": "张三"}, headers=teacher_headers
    )
    assert response.status_code == 403


def test_未登录看学生列表返回401(client):
    assert client.get("/api/students").status_code == 401


# ── 列表：余额 ────────────────────────────────────


def test_学生列表带余额(client, session, admin_headers, make_student):
    student = make_student(name="张三")
    _add_txn(session, student.id, 10.0)

    response = client.get("/api/students", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()[0]["remaining_hours"] == 10.0


def test_没有流水的学生余额显示0(client, admin_headers, make_student):
    """★ LEFT JOIN + coalesce 的意义所在。

    写成 INNER JOIN 的话，这条记录会**整个从列表里消失**，
    而不是显示 0 —— 那样的 bug 很难一眼看出来。
    """
    make_student(name="从没充过课时的学生")

    response = client.get("/api/students", headers=admin_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["remaining_hours"] == 0


def test_余额是正负流水求和(client, session, admin_headers, make_student):
    student = make_student(name="张三")
    _add_txn(session, student.id, 20.0)
    _add_txn(session, student.id, -7.5, TxnType.consume)
    _add_txn(session, student.id, -2.5, TxnType.adjust)

    response = client.get("/api/students", headers=admin_headers)
    assert response.json()[0]["remaining_hours"] == 10.0


def test_一个学生的余额不会被班级数放大(
    client, session, admin_headers, make_class, make_student
):
    """★ 防 N+1 之外的另一半：JOIN 写错会把 SUM 放大成错的钱数。

    如果实现里同时 JOIN 了 class_students 和 hour_transactions，
    学生在 2 个班时 10 课时会显示成 20。
    """
    a = make_class(name="YDY001")
    b = make_class(name="YDE001", class_type="1对2", rate=100.0)
    student = make_student(name="张三")
    session.add(ClassStudent(class_id=a.id, student_id=student.id, joined_on=date(2026, 1, 1)))
    session.add(ClassStudent(class_id=b.id, student_id=student.id, joined_on=date(2026, 1, 1)))
    session.commit()
    _add_txn(session, student.id, 10.0)

    response = client.get("/api/students", headers=admin_headers)
    assert response.json()[0]["remaining_hours"] == 10.0


def test_按班级筛选学生(client, session, admin_headers, make_class, make_student):
    klass = make_class(name="YDY001")
    inside = make_student(name="在班的")
    make_student(name="不在班的")
    session.add(
        ClassStudent(class_id=klass.id, student_id=inside.id, joined_on=date(2026, 1, 1))
    )
    session.commit()

    response = client.get(f"/api/students?class_id={klass.id}", headers=admin_headers)
    assert [s["name"] for s in response.json()] == ["在班的"]


def test_按班级筛选不含已退班的(client, session, admin_headers, make_class, make_student):
    klass = make_class(name="YDY001")
    student = make_student(name="退班了的")
    session.add(
        ClassStudent(
            class_id=klass.id,
            student_id=student.id,
            joined_on=date(2026, 1, 1),
            left_on=date(2026, 6, 1),
        )
    )
    session.commit()

    response = client.get(f"/api/students?class_id={klass.id}", headers=admin_headers)
    assert response.json() == []


def test_按姓名搜索学生(client, admin_headers, make_student):
    make_student(name="张三")
    make_student(name="李四")

    response = client.get("/api/students?q=张", headers=admin_headers)
    assert [s["name"] for s in response.json()] == ["张三"]


def test_按手机号搜索学生(client, admin_headers, make_student):
    make_student(name="张三", phone="13800001111")
    make_student(name="李四", phone="13900002222")

    response = client.get("/api/students?q=1390", headers=admin_headers)
    assert [s["name"] for s in response.json()] == ["李四"]


def test_搜索不会因为学生没手机号而漏掉(
    client, admin_headers, make_student
):
    """手机号是 NULL 时 `LIKE` 会返回 NULL 而不是 false，要 coalesce 兜住。"""
    make_student(name="张三")  # 不给手机号

    response = client.get("/api/students?q=张", headers=admin_headers)
    assert [s["name"] for s in response.json()] == ["张三"]


def test_默认能看到停用的学生_按参数过滤(client, admin_headers, make_student):
    make_student(name="在用的")
    make_student(name="停用的", is_active=False)

    all_rows = client.get("/api/students", headers=admin_headers).json()
    assert len(all_rows) == 2

    active = client.get("/api/students?is_active=true", headers=admin_headers).json()
    assert [s["name"] for s in active] == ["在用的"]


# ── 详情 ──────────────────────────────────────────


def test_学生详情含余额班级和出勤统计(
    client, session, admin_headers, make_class, make_student
):
    klass = make_class(name="YDY001")
    student = make_student(name="张三")
    session.add(
        ClassStudent(class_id=klass.id, student_id=student.id, joined_on=date(2026, 1, 1))
    )
    session.commit()
    _add_txn(session, student.id, 10.0)

    response = client.get(f"/api/students/{student.id}", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["remaining_hours"] == 10.0
    assert [c["name"] for c in body["classes"]] == ["YDY001"]
    # 考勤还没做，但形状已经定死了
    assert body["attendance"] == {"present": 0, "leave": 0, "absent": 0}


def test_学生详情_所属班级不含已退班的(
    client, session, admin_headers, make_class, make_student
):
    klass = make_class(name="YDY001")
    student = make_student(name="张三")
    session.add(
        ClassStudent(
            class_id=klass.id,
            student_id=student.id,
            joined_on=date(2026, 1, 1),
            left_on=date(2026, 6, 1),
        )
    )
    session.commit()

    response = client.get(f"/api/students/{student.id}", headers=admin_headers)
    assert response.json()["classes"] == []


def test_学生不存在返回404(client, admin_headers):
    assert client.get("/api/students/999", headers=admin_headers).status_code == 404


# ── 改 / 停用 ─────────────────────────────────────


def test_改学生资料(client, admin_headers, make_student):
    student = make_student(name="张三")
    response = client.patch(
        f"/api/students/{student.id}",
        json={"name": "张三丰", "gender": "男", "is_adult": True, "note": "改过了"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "张三丰"
    assert body["is_adult"] is True
    assert body["note"] == "改过了"


def test_改学生_能把成年状态改回未知(client, admin_headers, make_student):
    """★ 三态字段的经典坑。

    `is_adult` 的「未填」就是 null，跟「没传这个字段」长得一样。
    用 `if payload.is_adult is not None` 判断的话，一旦设过成年/未成年，
    界面把它改回「未填」会**静默失败** —— 提交成功、值没变。
    """
    student = make_student(name="张三", is_adult=True)

    response = client.patch(
        f"/api/students/{student.id}", json={"is_adult": None}, headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["is_adult"] is None


def test_改学生_能把手机号清空(client, admin_headers, make_student):
    student = make_student(name="张三", phone="13800001111")

    response = client.patch(
        f"/api/students/{student.id}", json={"phone": None}, headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["phone"] is None


def test_改学生_能把性别改回未填(client, admin_headers, make_student):
    student = make_student(name="张三", gender="男")

    response = client.patch(
        f"/api/students/{student.id}", json={"gender": ""}, headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["gender"] == ""


def test_改学生_没传的字段不会被清空(client, admin_headers, make_student):
    """反向保证：只改备注，不该把性别/成年/手机号一起抹了。"""
    student = make_student(
        name="张三", gender="男", is_adult=True, phone="13800001111"
    )

    response = client.patch(
        f"/api/students/{student.id}", json={"note": "只改备注"}, headers=admin_headers
    )
    body = response.json()
    assert body["gender"] == "男"
    assert body["is_adult"] is True
    assert body["phone"] == "13800001111"


def test_改学生_性别非法返回400(client, admin_headers, make_student):
    student = make_student(name="张三")
    response = client.patch(
        f"/api/students/{student.id}", json={"gender": "男男"}, headers=admin_headers
    )
    assert response.status_code == 400


def test_停用学生是软删(client, session, admin_headers, make_student):
    """学生的 DELETE 是软删 —— 真删了余额就再也算不出来。"""
    student = make_student(name="张三")
    _add_txn(session, student.id, 10.0)

    response = client.delete(f"/api/students/{student.id}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    session.expire_all()
    assert session.exec(select(Student)).first() is not None  # 行还在
    assert session.exec(select(HourTransaction)).first() is not None  # 流水也在


def test_重复停用返回400(client, admin_headers, make_student):
    student = make_student(name="张三")
    client.delete(f"/api/students/{student.id}", headers=admin_headers)
    again = client.delete(f"/api/students/{student.id}", headers=admin_headers)
    assert again.status_code == 400


def test_老师删学生返回403(client, teacher_headers, make_student):
    student = make_student(name="张三")
    response = client.delete(f"/api/students/{student.id}", headers=teacher_headers)
    assert response.status_code == 403
