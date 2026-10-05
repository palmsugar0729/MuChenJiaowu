"""班级接口 + 在册关系的测试。

老师只读、管理员可写；前缀规则；批量入班的「全有或全无」；
以及最容易写错的**重新入班必须复用原行**。
"""

from datetime import date, time

from sqlmodel import select

from app.models import Class, ClassStudent, Lesson, User  # noqa: F401


def _rows(session, model):
    """强制从库里重新读，避开 session 的身份映射缓存。

    接口是在另一个 session 里改的库，缓存不刷新会读到过期对象。
    """
    session.expire_all()
    return list(session.exec(select(model)))


# ── 建班级：前缀规则 ──────────────────────────────


def test_建班级_YDY前缀自动定为1对1(client, admin_headers):
    response = client.post("/api/classes", json={"name": "YDY001"}, headers=admin_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["class_type"] == "1对1"
    assert body["rate"] == 80  # 缺省按类型自动填


def test_建班级_YDE前缀自动定为1对2(client, admin_headers):
    response = client.post("/api/classes", json={"name": "YDE001"}, headers=admin_headers)
    assert response.status_code == 201
    assert response.json()["class_type"] == "1对2"


def test_建班级_前缀之后的内容不参与判定(client, admin_headers):
    response = client.post("/api/classes", json={"name": "ydy999xyz"}, headers=admin_headers)
    assert response.status_code == 201
    assert response.json()["class_type"] == "1对1"


def test_建班级_XB前缀不指定类型返回400(client, admin_headers):
    """小班必须自己选几人 —— 这是文档的硬要求。"""
    response = client.post("/api/classes", json={"name": "XB001"}, headers=admin_headers)
    assert response.status_code == 400
    assert "XB" in response.json()["detail"]


def test_建班级_XB前缀指定合法类型成功(client, admin_headers):
    response = client.post(
        "/api/classes",
        json={"name": "XB001", "class_type": "1对4"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    assert response.json()["rate"] == 110


def test_建班级_XB前缀指定非小班类型返回400(client, admin_headers):
    response = client.post(
        "/api/classes",
        json={"name": "XB001", "class_type": "1对1"},
        headers=admin_headers,
    )
    assert response.status_code == 400


def test_建班级_前缀与显式类型不符返回400(client, admin_headers):
    response = client.post(
        "/api/classes",
        json={"name": "YDY001", "class_type": "1对2"},
        headers=admin_headers,
    )
    assert response.status_code == 400
    assert "1对1" in response.json()["detail"]


def test_建班级_认不出前缀时必须显式给类型(client, admin_headers):
    response = client.post("/api/classes", json={"name": "随便叫什么"}, headers=admin_headers)
    assert response.status_code == 400


def test_建班级_未知类型且没给rate返回400(client, admin_headers):
    """不允许静默落到 DEFAULT_RATE —— 那会录进一个错价，等发工资才发现。"""
    response = client.post(
        "/api/classes",
        json={"name": "实验班", "class_type": "1对9"},
        headers=admin_headers,
    )
    assert response.status_code == 400
    assert "费率" in response.json()["detail"]


def test_建班级_显式rate以传的为准(client, admin_headers):
    response = client.post(
        "/api/classes",
        json={"name": "YDY002", "rate": 95.5},
        headers=admin_headers,
    )
    assert response.status_code == 201
    assert response.json()["rate"] == 95.5


def test_建班级_费率为负返回400(client, admin_headers):
    response = client.post(
        "/api/classes", json={"name": "YDY003", "rate": -1}, headers=admin_headers
    )
    assert response.status_code == 400


def test_建班级_重名返回400(client, admin_headers):
    client.post("/api/classes", json={"name": "YDY001"}, headers=admin_headers)
    response = client.post("/api/classes", json={"name": "YDY001"}, headers=admin_headers)
    assert response.status_code == 400
    assert "已存在" in response.json()["detail"]


# ── 权限 ──────────────────────────────────────────


def test_老师建班级返回403(client, teacher_headers):
    response = client.post("/api/classes", json={"name": "YDY001"}, headers=teacher_headers)
    assert response.status_code == 403


def test_老师能看班级列表(client, teacher_headers, make_class):
    make_class(name="YDY001")
    response = client.get("/api/classes", headers=teacher_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_班级列表带在册人数(client, session, admin_headers, make_class, make_student):
    klass = make_class(name="YDY001")
    make_class(name="YDE001", class_type="1对2", rate=100.0)
    for name in ("张三", "李四"):
        student = make_student(name=name)
        client.post(
            f"/api/classes/{klass.id}/students",
            json={"student_ids": [student.id], "joined_on": "2026-01-01"},
            headers=admin_headers,
        )

    rows = {c["name"]: c["student_count"] for c in client.get("/api/classes", headers=admin_headers).json()}
    assert rows == {"YDY001": 2, "YDE001": 0}  # ★ 没人也是 0，不是从列表里消失


def test_班级列表的人数不含已退班的(
    client, session, admin_headers, make_class, make_student
):
    klass = make_class(name="YDY001")
    student = make_student(name="张三")
    client.post(
        f"/api/classes/{klass.id}/students",
        json={"student_ids": [student.id], "joined_on": "2026-01-01"},
        headers=admin_headers,
    )
    client.delete(f"/api/classes/{klass.id}/students/{student.id}", headers=admin_headers)

    assert client.get("/api/classes", headers=admin_headers).json()[0]["student_count"] == 0


def test_超管也能建班级(client, super_admin_headers):
    """require_admin 必须包含超管，否则超管会被自己的系统挡在门外。"""
    response = client.post("/api/classes", json={"name": "YDY001"}, headers=super_admin_headers)
    assert response.status_code == 201


def test_未登录看班级列表返回401(client):
    assert client.get("/api/classes").status_code == 401


# ── 规则接口的路由顺序 ────────────────────────────


def test_规则接口没有被班级id路由挡住(client, teacher_headers):
    """回归：`/classes/rules` 必须声明在 `/classes/{class_id}` 之前。

    顺序写反的话，`class_id: int` 匹配不上 "rules"，FastAPI 直接回 422
    而且**不会继续往下找路由** —— 这个接口就永远用不了。
    """
    response = client.get("/api/classes/rules", headers=teacher_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["rates"]["1对1"] == 80
    assert body["small_prefix"] == "XB"
    assert body["small_types"] == ["1对3", "1对4", "1对5"]
    assert ["YDY", "1对1"] in body["class_name_rules"]


# ── 详情 ──────────────────────────────────────────


def test_班级详情含在册学生和累计已上课时(
    client, session, admin_headers, make_class, make_student
):
    klass = make_class(name="YDY001")
    student = make_student(name="张三")
    client.post(
        f"/api/classes/{klass.id}/students",
        json={"student_ids": [student.id], "joined_on": "2026-01-01"},
        headers=admin_headers,
    )

    response = client.get(f"/api/classes/{klass.id}", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["student_count"] == 1
    assert body["students"][0]["name"] == "张三"
    assert body["total_hours"] == 0.0  # 本轮还没有课程，但字段已经在了
    assert body["has_lessons"] is False  # 前端靠它决定删不删得动


def test_班级不存在返回404(client, admin_headers):
    assert client.get("/api/classes/999", headers=admin_headers).status_code == 404


# ── 删除 ──────────────────────────────────────────


def test_删没有课程的班级是真删(client, session, admin_headers, make_class):
    klass = make_class(name="YDY001")
    class_id = klass.id

    response = client.delete(f"/api/classes/{class_id}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["name"] == "YDY001"  # 回的是被删掉的那份数据
    assert _rows(session, Class) == []


def test_删班级会连在册关系一起清掉(
    client, session, admin_headers, make_class, make_student
):
    """外键是开的，不先删关联行会撞 FK 约束。"""
    klass = make_class(name="YDY001")
    student = make_student(name="张三")
    client.post(
        f"/api/classes/{klass.id}/students",
        json={"student_ids": [student.id], "joined_on": "2026-01-01"},
        headers=admin_headers,
    )

    response = client.delete(f"/api/classes/{klass.id}", headers=admin_headers)
    assert response.status_code == 200
    assert _rows(session, ClassStudent) == []
    assert len(_rows(session, type(student))) == 1  # 学生本身不动


def test_删有课程的班级返回400(
    client, session, admin_headers, make_class, make_user
):
    """排过课就不许删，只能停用 —— 否则那些课成了孤儿，工资表追溯不回去。"""
    teacher = make_user("13900000010")
    klass = make_class(name="YDY001")
    session.add(
        Lesson(
            class_id=klass.id,
            teacher_id=teacher.id,
            lesson_date=date(2026, 10, 1),
            start_time=time(9, 0),
            hours=1.0,
            rate=80.0,
        )
    )
    session.commit()

    # 详情先告诉前端「删不动」，界面才不用等用户点了才弹 400
    assert client.get(f"/api/classes/{klass.id}", headers=admin_headers).json()[
        "has_lessons"
    ] is True

    response = client.delete(f"/api/classes/{klass.id}", headers=admin_headers)
    assert response.status_code == 400
    assert "课程记录" in response.json()["detail"]
    assert len(_rows(session, Class)) == 1  # 没被删掉


def test_老师删班级返回403(client, make_class, teacher_headers):
    klass = make_class(name="YDY001")
    response = client.delete(f"/api/classes/{klass.id}", headers=teacher_headers)
    assert response.status_code == 403


# ── 在册关系 ──────────────────────────────────────


def test_批量加学生入班(client, session, admin_headers, make_class, make_student):
    klass = make_class(name="YDY001")
    a = make_student(name="张三")
    b = make_student(name="李四")

    response = client.post(
        f"/api/classes/{klass.id}/students",
        json={"student_ids": [a.id, b.id], "joined_on": "2026-01-01"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    assert len(response.json()) == 2
    assert len(_rows(session, ClassStudent)) == 2


def test_批量加学生_有一个无效则全都不加(
    client, session, admin_headers, make_class, make_student
):
    """全有或全无 —— 部分成功会让调用方不知道该不该重试。"""
    klass = make_class(name="YDY001")
    good = make_student(name="张三")

    response = client.post(
        f"/api/classes/{klass.id}/students",
        json={"student_ids": [good.id, 99999], "joined_on": "2026-01-01"},
        headers=admin_headers,
    )
    assert response.status_code == 400
    assert "99999" in response.json()["detail"]
    assert _rows(session, ClassStudent) == []  # ★ 一个都没写进去


def test_停用的学生不能入班(client, session, admin_headers, make_class, make_student):
    klass = make_class(name="YDY001")
    student = make_student(name="张三", is_active=False)

    response = client.post(
        f"/api/classes/{klass.id}/students",
        json={"student_ids": [student.id], "joined_on": "2026-01-01"},
        headers=admin_headers,
    )
    assert response.status_code == 400
    assert _rows(session, ClassStudent) == []


def test_重复加同一学生不新建行(client, session, admin_headers, make_class, make_student):
    klass = make_class(name="YDY001")
    student = make_student(name="张三")
    payload = {"student_ids": [student.id], "joined_on": "2026-01-01"}

    client.post(f"/api/classes/{klass.id}/students", json=payload, headers=admin_headers)
    response = client.post(
        f"/api/classes/{klass.id}/students", json=payload, headers=admin_headers
    )

    assert response.status_code == 201  # 幂等：不报错
    assert len(_rows(session, ClassStudent)) == 1


def test_同一个学生在同一次请求里传两次只建一行(
    client, session, admin_headers, make_class, make_student
):
    klass = make_class(name="YDY001")
    student = make_student(name="张三")

    client.post(
        f"/api/classes/{klass.id}/students",
        json={"student_ids": [student.id, student.id], "joined_on": "2026-01-01"},
        headers=admin_headers,
    )
    assert len(_rows(session, ClassStudent)) == 1


def test_退班写left_on不物理删除(
    client, session, admin_headers, make_class, make_student
):
    klass = make_class(name="YDY001")
    student = make_student(name="张三")
    client.post(
        f"/api/classes/{klass.id}/students",
        json={"student_ids": [student.id], "joined_on": "2026-01-01"},
        headers=admin_headers,
    )

    response = client.delete(
        f"/api/classes/{klass.id}/students/{student.id}?left_on=2026-06-30",
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["left_on"] == "2026-06-30"

    rows = _rows(session, ClassStudent)
    assert len(rows) == 1  # ★ 行还在
    assert rows[0].left_on == date(2026, 6, 30)


def test_已退班学生不出现在在册列表和详情(
    client, admin_headers, make_class, make_student
):
    klass = make_class(name="YDY001")
    student = make_student(name="张三")
    client.post(
        f"/api/classes/{klass.id}/students",
        json={"student_ids": [student.id], "joined_on": "2026-01-01"},
        headers=admin_headers,
    )
    client.delete(f"/api/classes/{klass.id}/students/{student.id}", headers=admin_headers)

    assert client.get(
        f"/api/classes/{klass.id}/students", headers=admin_headers
    ).json() == []
    assert client.get(f"/api/classes/{klass.id}", headers=admin_headers).json()[
        "student_count"
    ] == 0


def test_退班再入班复用原行不新建(
    client, session, admin_headers, make_class, make_student
):
    """★ 最容易写错的一处。

    `ix_cs_pair` 是 (class_id, student_id) **全表唯一** ——
    退班再入班必须复用原来的行，直接 INSERT 会撞唯一索引。
    """
    klass = make_class(name="YDY001")
    student = make_student(name="张三")

    client.post(
        f"/api/classes/{klass.id}/students",
        json={"student_ids": [student.id], "joined_on": "2026-01-01"},
        headers=admin_headers,
    )
    original_id = _rows(session, ClassStudent)[0].id

    client.delete(f"/api/classes/{klass.id}/students/{student.id}", headers=admin_headers)
    response = client.post(
        f"/api/classes/{klass.id}/students",
        json={"student_ids": [student.id], "joined_on": "2026-06-01"},
        headers=admin_headers,
    )
    assert response.status_code == 201

    rows = _rows(session, ClassStudent)
    assert len(rows) == 1, "退班再入班不该新建第二行"
    assert rows[0].id == original_id, "应该复用原来那一行"
    assert rows[0].left_on is None, "重新入班要清掉 left_on"
    assert rows[0].joined_on == date(2026, 6, 1)


def test_学生可同时在多个班(client, session, admin_headers, make_class, make_student):
    a = make_class(name="YDY001")
    b = make_class(name="YDE001", class_type="1对2", rate=100.0)
    student = make_student(name="张三")

    for klass in (a, b):
        response = client.post(
            f"/api/classes/{klass.id}/students",
            json={"student_ids": [student.id], "joined_on": "2026-01-01"},
            headers=admin_headers,
        )
        assert response.status_code == 201

    assert len(_rows(session, ClassStudent)) == 2


def test_重复退班返回404(client, admin_headers, make_class, make_student):
    klass = make_class(name="YDY001")
    student = make_student(name="张三")
    client.post(
        f"/api/classes/{klass.id}/students",
        json={"student_ids": [student.id], "joined_on": "2026-01-01"},
        headers=admin_headers,
    )

    client.delete(f"/api/classes/{klass.id}/students/{student.id}", headers=admin_headers)
    again = client.delete(
        f"/api/classes/{klass.id}/students/{student.id}", headers=admin_headers
    )
    assert again.status_code == 404


# ── 改班级 ────────────────────────────────────────


def test_改班级类型不自动改费率(client, admin_headers, make_class):
    """费率是钱，改类型顺手改价会悄无声息地影响将来的工资表。"""
    klass = make_class(name="随便叫什么", class_type="1对1", rate=88.0)

    response = client.patch(
        f"/api/classes/{klass.id}", json={"class_type": "1对2"}, headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["class_type"] == "1对2"
    assert response.json()["rate"] == 88.0  # ★ 没跟着变


def test_费率只在显式提供时才改(client, admin_headers, make_class):
    klass = make_class(name="YDY001", rate=80.0)
    response = client.patch(
        f"/api/classes/{klass.id}", json={"note": "改个备注"}, headers=admin_headers
    )
    assert response.json()["rate"] == 80.0


def test_改班级名让固定前缀强制对齐类型(client, admin_headers, make_class):
    klass = make_class(name="随便叫什么", class_type="1对2", rate=100.0)

    response = client.patch(
        f"/api/classes/{klass.id}", json={"name": "YDY007"}, headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["class_type"] == "1对1"  # 前缀重新推断了


def test_改班级名撞车返回400(client, admin_headers, make_class):
    make_class(name="YDY001")
    other = make_class(name="YDY002", class_type="1对1", rate=80.0)

    response = client.patch(
        f"/api/classes/{other.id}", json={"name": "YDY001"}, headers=admin_headers
    )
    assert response.status_code == 400


def test_改班级名成自己的名字不算撞车(client, admin_headers, make_class):
    klass = make_class(name="YDY001")
    response = client.patch(
        f"/api/classes/{klass.id}", json={"name": "YDY001", "note": "x"}, headers=admin_headers
    )
    assert response.status_code == 200


def test_停用班级走PATCH而不是DELETE(client, admin_headers, make_class):
    klass = make_class(name="YDY001")
    response = client.patch(
        f"/api/classes/{klass.id}", json={"is_active": False}, headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    # 停用后仍能按 is_active 过滤出来
    assert client.get(
        "/api/classes?is_active=false", headers=admin_headers
    ).json()[0]["name"] == "YDY001"


def test_建班级时note会去掉首尾空格(client, admin_headers):
    response = client.post(
        "/api/classes", json={"name": "YDY001", "note": "  周末班  "}, headers=admin_headers
    )
    assert response.json()["note"] == "周末班"
