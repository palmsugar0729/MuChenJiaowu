"""账号管理 + 角色护栏（实施计划 5.2）。

Phase 1 的验收标准就在这个文件里：老师调 `/admin/users` 必须 403。
"""

import pytest

from app.models import Role, User
from app.services.users import assert_not_last_super_admin, active_super_admin_count
from tests.conftest import DEFAULT_PASSWORD

ADMIN = "/api/admin/users"


@pytest.fixture
def super_admin(make_user):
    return make_user("13900000001", role=Role.super_admin, display_name="超管")


@pytest.fixture
def admin(make_user):
    return make_user("13900000002", role=Role.admin, display_name="管理员")


@pytest.fixture
def teacher(make_user):
    return make_user("13800000001", role=Role.teacher, display_name="梁筱")


# ── 老师一律进不来（Phase 1 验收标准）──────────────


def test_老师调账号管理接口返回403(client, teacher, headers_for):
    resp = client.get(ADMIN, headers=headers_for(teacher))
    assert resp.status_code == 403


def test_老师建不了号(client, teacher, headers_for):
    resp = client.post(
        ADMIN,
        json={"phone": "13700000001", "display_name": "偷偷建的"},
        headers=headers_for(teacher),
    )
    assert resp.status_code == 403


def test_老师改不了别人的号(client, teacher, headers_for):
    resp = client.patch(
        f"{ADMIN}/{teacher.id}", json={"display_name": "改自己"}, headers=headers_for(teacher)
    )
    assert resp.status_code == 403


# ── 建号 ──────────────────────────────────────────


def test_超管建老师号返回一次性初始密码(client, super_admin, headers_for):
    resp = client.post(
        ADMIN,
        json={"phone": "13800000001", "display_name": "梁筱", "role": "teacher"},
        headers=headers_for(super_admin),
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["user"]["display_name"] == "梁筱"
    assert body["user"]["role"] == "teacher"
    assert len(body["initial_password"]) == 10


def test_拿初始密码能直接登录且被要求改密(client, super_admin, headers_for):
    """这就是 Phase 1 验收里那条完整链路。"""
    created = client.post(
        ADMIN,
        json={"phone": "13800000001", "display_name": "梁筱"},
        headers=headers_for(super_admin),
    ).json()

    login = client.post(
        "/api/auth/login",
        json={"phone": "13800000001", "password": created["initial_password"]},
    )

    assert login.status_code == 200
    assert login.json()["user"]["must_change_password"] is True


def test_管理员建得了老师号(client, admin, headers_for):
    resp = client.post(
        ADMIN,
        json={"phone": "13800000001", "display_name": "梁筱"},
        headers=headers_for(admin),
    )
    assert resp.status_code == 201


def test_管理员建不了管理员号(client, admin, headers_for):
    """防的是管理员互相拆台 —— 两个管理员能互删，管理就失控了。"""
    for role in ("admin", "super_admin"):
        resp = client.post(
            ADMIN,
            json={"phone": "13800000009", "display_name": "新管理员", "role": role},
            headers=headers_for(admin),
        )
        assert resp.status_code == 403, role


def test_超管建得了管理员号(client, super_admin, headers_for):
    resp = client.post(
        ADMIN,
        json={"phone": "13900000009", "display_name": "新管理员", "role": "admin"},
        headers=headers_for(super_admin),
    )
    assert resp.status_code == 201
    assert resp.json()["user"]["role"] == "admin"


def test_手机号重复建不进去(client, super_admin, headers_for, teacher):
    resp = client.post(
        ADMIN,
        json={"phone": teacher.phone, "display_name": "撞号的"},
        headers=headers_for(super_admin),
    )

    assert resp.status_code == 400
    assert "占用" in resp.json()["detail"]


def test_手机号或姓名为空会被挡(client, super_admin, headers_for):
    for payload in (
        {"phone": "  ", "display_name": "没手机号"},
        {"phone": "13800000001", "display_name": "   "},
    ):
        resp = client.post(ADMIN, json=payload, headers=headers_for(super_admin))
        assert resp.status_code == 400, payload


# ── 列表 ──────────────────────────────────────────


def test_管理员能看列表(client, admin, headers_for, teacher):
    """列表是全员名册（含超管），只是**改不了**管不了的那些号。

    小机构里都是同事，知道自己有哪些同事是正常的；真正的闸门在写操作上。
    """
    resp = client.get(ADMIN, headers=headers_for(admin))

    assert resp.status_code == 200
    phones = [u["phone"] for u in resp.json()]
    assert teacher.phone in phones
    assert admin.phone in phones


def test_列表能按角色和启用状态过滤(client, super_admin, admin, teacher, headers_for):
    headers = headers_for(super_admin)

    assert len(client.get(ADMIN, headers=headers).json()) == 3
    assert len(client.get(f"{ADMIN}?role=teacher", headers=headers).json()) == 1
    assert len(client.get(f"{ADMIN}?role=admin", headers=headers).json()) == 1
    assert len(client.get(f"{ADMIN}?is_active=false", headers=headers).json()) == 0


def test_列表里也没有密码哈希(client, super_admin, headers_for, teacher):
    resp = client.get(ADMIN, headers=headers_for(super_admin))

    assert teacher.password_hash not in resp.text
    assert "password_hash" not in resp.text


# ── 改账号 ────────────────────────────────────────


def test_超管能改管理员的姓名(client, super_admin, admin, headers_for):
    resp = client.patch(
        f"{ADMIN}/{admin.id}",
        json={"display_name": "改了名"},
        headers=headers_for(super_admin),
    )

    assert resp.status_code == 200
    assert resp.json()["display_name"] == "改了名"


def test_管理员改不了管理员(client, admin, headers_for, make_user):
    another = make_user("13900000003", role=Role.admin)

    resp = client.patch(
        f"{ADMIN}/{another.id}",
        json={"display_name": "篡改"},
        headers=headers_for(admin),
    )
    assert resp.status_code == 403


def test_管理员改得了老师(client, admin, teacher, headers_for):
    resp = client.patch(
        f"{ADMIN}/{teacher.id}",
        json={"display_name": "梁筱（改）"},
        headers=headers_for(admin),
    )
    assert resp.status_code == 200


def test_改角色这条路根本不存在(client, super_admin, teacher, headers_for, session):
    """角色不在可改字段里 —— 想换角色就新建号（历史记录存的是 user.id）。"""
    resp = client.patch(
        f"{ADMIN}/{teacher.id}",
        json={"role": "admin"},
        headers=headers_for(super_admin),
    )

    assert resp.status_code == 200  # 请求本身合法
    session.refresh(teacher)
    assert teacher.role == Role.teacher  # 但角色纹丝不动


def test_改手机号撞号会被挡(client, admin, teacher, headers_for, make_user):
    other = make_user("13800000002")

    resp = client.patch(
        f"{ADMIN}/{teacher.id}",
        json={"phone": other.phone},
        headers=headers_for(admin),
    )
    assert resp.status_code == 400


def test_改不存在的账号返回404(client, super_admin, headers_for):
    resp = client.patch(
        f"{ADMIN}/99999", json={"display_name": "幽灵"}, headers=headers_for(super_admin)
    )
    assert resp.status_code == 404


# ── 停用（软删）───────────────────────────────────


def test_停用是软删记录还在(client, admin, teacher, headers_for, session):
    """账号挂在历史课程和审批记录上，真删了历史就成了孤儿。"""
    resp = client.delete(f"{ADMIN}/{teacher.id}", headers=headers_for(admin))
    assert resp.status_code == 200

    session.expire_all()
    still_there = session.get(User, teacher.id)
    assert still_there is not None
    assert still_there.is_active is False


def test_停用后本人登不进来(client, admin, teacher, headers_for):
    client.delete(f"{ADMIN}/{teacher.id}", headers=headers_for(admin))

    resp = client.post(
        "/api/auth/login",
        json={"phone": teacher.phone, "password": DEFAULT_PASSWORD},
    )
    assert resp.status_code == 403


def test_重复停用会提示已经停用了(client, admin, teacher, headers_for):
    client.delete(f"{ADMIN}/{teacher.id}", headers=headers_for(admin))

    resp = client.delete(f"{ADMIN}/{teacher.id}", headers=headers_for(admin))
    assert resp.status_code == 400


def test_停用后还能再启用回来(client, admin, teacher, headers_for):
    client.delete(f"{ADMIN}/{teacher.id}", headers=headers_for(admin))

    resp = client.patch(
        f"{ADMIN}/{teacher.id}", json={"is_active": True}, headers=headers_for(admin)
    )

    assert resp.status_code == 200
    assert resp.json()["is_active"] is True


def test_谁都不能停用自己(client, super_admin, headers_for):
    """手滑把自己关了就得找别人来救。"""
    resp = client.delete(f"{ADMIN}/{super_admin.id}", headers=headers_for(super_admin))
    assert resp.status_code == 400

    resp = client.patch(
        f"{ADMIN}/{super_admin.id}",
        json={"is_active": False},
        headers=headers_for(super_admin),
    )
    assert resp.status_code == 400


def test_超管能停用另一个超管(client, super_admin, headers_for, make_user):
    """有备份超管时才敢停 —— 这条也顺带说明系统不会没有超管。"""
    another = make_user("13900000009", role=Role.super_admin)

    resp = client.delete(f"{ADMIN}/{another.id}", headers=headers_for(super_admin))

    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


# ── 最后一个超管 ──────────────────────────────────


def test_最后一个超管的护栏本身是对的(session, super_admin):
    """这条护栏目前从接口走不到：

    停用超管必须由超管本人发起（自己不能停自己），所以只要还能发请求，
    场上就至少有一个启用中的超管，计数永远 >= 2。

    留着是因为「绝不能没有超管」是这个系统真正的底线，
    哪天有人放宽了「不能停用自己」，这里必须立刻兜住。
    """
    assert active_super_admin_count(session) == 1

    with pytest.raises(Exception) as caught:
        assert_not_last_super_admin(session, super_admin)

    assert "最后一个" in str(caught.value)


def test_有第二个超管时护栏放行(session, super_admin, make_user):
    another = make_user("13900000009", role=Role.super_admin)

    assert active_super_admin_count(session) == 2
    assert_not_last_super_admin(session, another)  # 不抛异常即通过


# ── 重置密码 ──────────────────────────────────────


def test_重置密码后新密码生效且要求重新改密(client, admin, teacher, headers_for):
    resp = client.post(
        f"{ADMIN}/{teacher.id}/reset-password", headers=headers_for(admin)
    )

    assert resp.status_code == 200
    new_password = resp.json()["initial_password"]

    login = client.post(
        "/api/auth/login",
        json={"phone": teacher.phone, "password": new_password},
    )
    assert login.status_code == 200
    assert login.json()["user"]["must_change_password"] is True


def test_重置密码后旧密码作废(client, admin, teacher, headers_for):
    client.post(f"{ADMIN}/{teacher.id}/reset-password", headers=headers_for(admin))

    login = client.post(
        "/api/auth/login",
        json={"phone": teacher.phone, "password": DEFAULT_PASSWORD},
    )
    assert login.status_code == 401


def test_管理员重置不了管理员的密码(client, admin, headers_for, make_user):
    another = make_user("13900000003", role=Role.admin)

    resp = client.post(
        f"{ADMIN}/{another.id}/reset-password", headers=headers_for(admin)
    )
    assert resp.status_code == 403


def test_超管能重置管理员的密码(client, super_admin, admin, headers_for):
    resp = client.post(
        f"{ADMIN}/{admin.id}/reset-password", headers=headers_for(super_admin)
    )
    assert resp.status_code == 200


def test_重置的密码不含易混字符(client, admin, teacher, headers_for):
    """初始密码要口头/微信转达，0O1lI 这种必须排除。"""
    resp = client.post(
        f"{ADMIN}/{teacher.id}/reset-password", headers=headers_for(admin)
    )
    assert not set(resp.json()["initial_password"]) & set("0O1lI")
