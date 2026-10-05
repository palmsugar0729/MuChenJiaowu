"""枚举 CHECK 约束的回归测试。

背景：SQLAlchemy 2.0 的 `Enum` 默认 `create_constraint=False`，这五个枚举列
一度全是裸 VARCHAR，什么值都塞得进去。

最要命的是 `hour_transactions.type`：`uq_consume_once` 这个防重复扣课时的部分
唯一索引，条件里押着 `'consume'` 这个字面量。写错大小写（`'Consume'`）索引会
**静默失效**，同一节课扣两次课时，而且没有任何报错。
"""

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.db import engine
from app.models import (
    ApprovalStatus,
    AttendanceStatus,
    LessonStatus,
    Role,
    TxnType,
)

# (表名, 约束名, 对应的 Python 枚举)
CASES = [
    ("users", "ck_users_role", Role),
    ("lessons", "ck_lessons_status", LessonStatus),
    ("attendance", "ck_attendance_status", AttendanceStatus),
    ("hour_transactions", "ck_hour_transactions_type", TxnType),
    ("approvals", "ck_approvals_status", ApprovalStatus),
]


@pytest.mark.parametrize("table,constraint_name,enum_cls", CASES)
def test_五个枚举的CHECK约束都建出来了(table, constraint_name, enum_cls):
    names = {c["name"] for c in inspect(engine).get_check_constraints(table)}
    assert constraint_name in names


@pytest.mark.parametrize("table,constraint_name,enum_cls", CASES)
def test_约束里的取值和Python枚举逐项一致(table, constraint_name, enum_cls):
    """约束是从枚举推导出来的，这条测的是「推导本身没写错」。

    如果哪天往枚举里加了成员却忘了重建库，这里会红。
    """
    sqltext = next(
        c["sqltext"]
        for c in inspect(engine).get_check_constraints(table)
        if c["name"] == constraint_name
    )
    for member in enum_cls:
        assert f"'{member.name}'" in sqltext


def test_写入非法role被数据库拒绝():
    """裸 SQL 直插，绕开 ORM —— 测的就是数据库那一层。

    ⚠️ 必须显式给 created_at：它的默认值是 Python 侧的 default_factory，
    裸 SQL 不生效，不给会先撞 NOT NULL 而不是撞 CHECK。
    """
    with pytest.raises(IntegrityError) as excinfo:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "insert into users "
                    "(phone, display_name, password_hash, role, is_active, "
                    " must_change_password, created_at) "
                    "values ('19000000000', 'x', 'h', 'SUPERADMIN', 1, 1, '2026-01-01')"
                )
            )
    assert "ck_users_role" in str(excinfo.value)


def test_写入非法type被数据库拒绝(make_student):
    # 先建个真学生：外键是开的，student_id 悬空的话会先撞 FK 而不是撞 CHECK
    student = make_student(name="张三")

    with pytest.raises(IntegrityError) as excinfo:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "insert into hour_transactions "
                    "(student_id, type, amount, note, created_at) "
                    f"values ({student.id}, 'Consume', -1.0, '', '2026-01-01')"
                )
            )
    assert "ck_hour_transactions_type" in str(excinfo.value)


def test_部分唯一索引uq_consume_once还在():
    """回归测试：改 `__table_args__` 时最容易漏掉这个索引。

    漏了就等于拆掉「防重复扣课时」的安全网，而且不会有任何报错。
    """
    indexes = {i["name"]: i for i in inspect(engine).get_indexes("hour_transactions")}
    assert "uq_consume_once" in indexes
    # SQLite 反射回来的是 1 而不是 True，这里只要求「真值」
    assert bool(indexes["uq_consume_once"]["unique"]) is True
    assert indexes["uq_consume_once"]["column_names"] == ["lesson_id", "student_id"]


def test_uq_consume_once的条件绑在枚举上():
    """索引里的 WHERE 字面量必须就是 `TxnType.consume` 的名字。

    这条把「索引条件」和「Python 枚举」钉死在一起：改枚举成员名而不同步索引，
    这里会红 —— 否则索引会静默失效。
    """
    with engine.begin() as conn:
        sql = conn.execute(
            text(
                "select sql from sqlite_master "
                "where type = 'index' and name = 'uq_consume_once'"
            )
        ).scalar()
    assert sql is not None
    assert f"'{TxnType.consume.name}'" in sql
