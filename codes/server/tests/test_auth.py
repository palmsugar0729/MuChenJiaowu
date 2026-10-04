"""登录、改密、个人信息（实施计划 5.1）。"""

from app.models import Role
from tests.conftest import DEFAULT_PASSWORD


# ── 登录 ──────────────────────────────────────────


def test_手机号加密码能换到token(client, make_user):
    teacher = make_user("13800000001", display_name="梁筱")

    resp = client.post(
        "/api/auth/login",
        json={"phone": teacher.phone, "password": DEFAULT_PASSWORD},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["display_name"] == "梁筱"
    assert body["user"]["role"] == "teacher"


def test_登录响应里绝不能出现密码哈希(client, make_user):
    """哪怕是哈希也不能漏出去 —— 拿到就能离线爆破。"""
    user = make_user("13800000001")

    resp = client.post(
        "/api/auth/login",
        json={"phone": "13800000001", "password": DEFAULT_PASSWORD},
    )

    assert user.password_hash not in resp.text
    assert "password_hash" not in resp.text


def test_密码错误返回401(client, make_user):
    make_user("13800000001")

    resp = client.post(
        "/api/auth/login",
        json={"phone": "13800000001", "password": "wrong-password"},
    )

    assert resp.status_code == 401


def test_手机号不存在和密码错误回同一句话(client, make_user):
    """不给撞库的人区分「这个号存在」的余地。"""
    make_user("13800000001")

    wrong_password = client.post(
        "/api/auth/login",
        json={"phone": "13800000001", "password": "wrong-password"},
    )
    unknown_phone = client.post(
        "/api/auth/login",
        json={"phone": "13900000000", "password": "wrong-password"},
    )

    assert wrong_password.status_code == unknown_phone.status_code == 401
    assert wrong_password.json()["detail"] == unknown_phone.json()["detail"]


def test_停用的账号登不进来且提示明确(client, make_user):
    """提示必须说「停用」—— 否则当事人只会以为自己密码记错了，反复试。"""
    user = make_user("13800000001", is_active=False)

    resp = client.post(
        "/api/auth/login",
        json={"phone": user.phone, "password": DEFAULT_PASSWORD},
    )

    assert resp.status_code == 403
    assert "停用" in resp.json()["detail"]


def test_首次登录会带上强制改密标记(client, make_user):
    """这个标记是前端跳改密页的依据。"""
    make_user("13800000001", must_change_password=True)

    resp = client.post(
        "/api/auth/login",
        json={"phone": "13800000001", "password": DEFAULT_PASSWORD},
    )

    assert resp.json()["user"]["must_change_password"] is True


# ── 当前用户 ──────────────────────────────────────


def test_不带token看不到自己的信息(client):
    assert client.get("/api/users/me").status_code == 401


def test_伪造的token进不来(client):
    resp = client.get(
        "/api/users/me", headers={"Authorization": "Bearer not.a.real.token"}
    )
    assert resp.status_code == 401


def test_停用后token立刻失效(client, make_user, headers_for, session):
    """停用不能等到 token 过期才生效 —— 人已经离职了，7 天内还能进来不像话。"""
    user = make_user("13800000001")
    headers = headers_for(user)
    assert client.get("/api/users/me", headers=headers).status_code == 200

    user.is_active = False
    session.add(user)
    session.commit()

    assert client.get("/api/users/me", headers=headers).status_code == 401


def test_能看到自己的信息(client, make_user, headers_for):
    user = make_user("13800000001", role=Role.admin)

    resp = client.get("/api/users/me", headers=headers_for(user))

    assert resp.status_code == 200
    assert resp.json()["phone"] == "13800000001"
    assert resp.json()["role"] == "admin"


# ── 改密码 ────────────────────────────────────────


def test_原密码不对改不了(client, make_user, headers_for):
    user = make_user("13800000001")

    resp = client.post(
        "/api/auth/change-password",
        json={"old_password": "nope", "new_password": "brand-new-pw"},
        headers=headers_for(user),
    )

    assert resp.status_code == 400


def test_新密码太短不给过(client, make_user, headers_for):
    user = make_user("13800000001")

    resp = client.post(
        "/api/auth/change-password",
        json={"old_password": DEFAULT_PASSWORD, "new_password": "12345"},
        headers=headers_for(user),
    )

    assert resp.status_code == 400


def test_新密码不能和原密码一样(client, make_user, headers_for):
    """强制改密的意义就在于换成一个只有自己知道的。"""
    user = make_user("13800000001")

    resp = client.post(
        "/api/auth/change-password",
        json={"old_password": DEFAULT_PASSWORD, "new_password": DEFAULT_PASSWORD},
        headers=headers_for(user),
    )

    assert resp.status_code == 400


def test_改密成功后新密码生效旧密码作废且标记清掉(client, make_user, headers_for):
    user = make_user("13800000001")

    resp = client.post(
        "/api/auth/change-password",
        json={"old_password": DEFAULT_PASSWORD, "new_password": "我的新密码123"},
        headers=headers_for(user),
    )
    assert resp.status_code == 200

    new_login = client.post(
        "/api/auth/login",
        json={"phone": "13800000001", "password": "我的新密码123"},
    )
    old_login = client.post(
        "/api/auth/login",
        json={"phone": "13800000001", "password": DEFAULT_PASSWORD},
    )

    assert new_login.status_code == 200
    assert new_login.json()["user"]["must_change_password"] is False
    assert old_login.status_code == 401


# ── 改自己的信息 ──────────────────────────────────


def test_能改自己的姓名(client, make_user, headers_for, session):
    user = make_user("13800000001", display_name="旧名字")

    resp = client.patch(
        "/api/users/me", json={"display_name": "新名字"}, headers=headers_for(user)
    )

    assert resp.status_code == 200
    assert resp.json()["display_name"] == "新名字"


def test_能改自己的手机号(client, make_user, headers_for):
    user = make_user("13800000001")

    resp = client.patch(
        "/api/users/me", json={"phone": "13900000009"}, headers=headers_for(user)
    )

    assert resp.status_code == 200
    assert resp.json()["phone"] == "13900000009"


def test_改成别人已占用的手机号会被挡(client, make_user, headers_for):
    """手机号是登录标识，撞了两个人就有一个登不进来。"""
    me = make_user("13800000001")
    make_user("13800000002")

    resp = client.patch(
        "/api/users/me", json={"phone": "13800000002"}, headers=headers_for(me)
    )

    assert resp.status_code == 400


def test_改自己的手机号但不改也能过(client, make_user, headers_for):
    """唯一性校验得把自己排除掉，否则「只改姓名」会被自己的手机号卡住。"""
    user = make_user("13800000001")

    resp = client.patch(
        "/api/users/me",
        json={"phone": "13800000001", "display_name": "改个名"},
        headers=headers_for(user),
    )

    assert resp.status_code == 200


def test_不能通过改自己信息来停用自己(client, make_user, headers_for):
    user = make_user("13800000001")

    resp = client.patch(
        "/api/users/me", json={"is_active": False}, headers=headers_for(user)
    )

    assert resp.status_code == 400
