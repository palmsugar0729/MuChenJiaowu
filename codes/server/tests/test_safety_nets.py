"""验证「钱算得对」的几条安全网。

这些是整个系统最不能出错的地方 —— 一旦错，就是学生课时和家长对不上账。
"""

from datetime import date, time

import pytest
from sqlalchemy import func, inspect as sa_inspect
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_password,
    hash_password,
    verify_password,
)
from app.models import (
    Class,
    HourTransaction,
    Lesson,
    Role,
    Student,
    TxnType,
    User,
)


# ── 夹具 ──────────────────────────────────────────


@pytest.fixture
def teacher(session):
    user = User(
        phone="13800000001",
        display_name="梁筱",
        password_hash=hash_password("pw"),
        role=Role.teacher,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture
def klass(session):
    item = Class(name="沐晨提高班", class_type="1对1", rate=80.0)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@pytest.fixture
def students(session):
    people = [Student(name="小明"), Student(name="小红")]
    session.add_all(people)
    session.commit()
    for person in people:
        session.refresh(person)
    return people


@pytest.fixture
def lesson(session, klass, teacher):
    item = Lesson(
        class_id=klass.id,
        teacher_id=teacher.id,
        lesson_date=date(2026, 9, 26),
        start_time=time(9, 0),
        hours=2.5,
        rate=klass.rate,
        created_by=teacher.id,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def balance_of(session, student_id: int) -> float:
    """学生所剩课时 = 流水求和。"""
    return session.exec(
        select(func.coalesce(func.sum(HourTransaction.amount), 0.0)).where(
            HourTransaction.student_id == student_id
        )
    ).one()


# ── 安全网 1：不能重复扣课时 ────────────────────────


def test_部分唯一索引确实建出来了(session):
    """如果哪天有人重构 models 把它删了，这条会立刻报警。"""
    indexes = sa_inspect(session.get_bind()).get_indexes("hour_transactions")
    names = {item["name"] for item in indexes}
    assert "uq_consume_once" in names


def test_同一节课不能对同一学生扣两次课时(session, lesson, students):
    """老师误点两次「完成上课」、或网络重试导致请求重发，都扣不了第二遍。"""
    xiaoming = students[0]
    consume = dict(
        student_id=xiaoming.id,
        type=TxnType.consume,
        amount=-2.5,
        lesson_id=lesson.id,
    )

    session.add(HourTransaction(**consume))
    session.commit()

    session.add(HourTransaction(**consume))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    assert balance_of(session, xiaoming.id) == -2.5


def test_同一节课可以扣不同学生的课时(session, lesson, students):
    """唯一索引是 (lesson_id, student_id) 组合，不是 lesson_id 本身。"""
    for person in students:
        session.add(
            HourTransaction(
                student_id=person.id,
                type=TxnType.consume,
                amount=-2.5,
                lesson_id=lesson.id,
            )
        )
    session.commit()

    for person in students:
        assert balance_of(session, person.id) == -2.5


def test_购买课时不受唯一索引限制(session, students):
    """部分唯一索引只约束 type='consume'，正常购买可以买很多次。"""
    xiaoming = students[0]
    for _ in range(3):
        session.add(
            HourTransaction(
                student_id=xiaoming.id, type=TxnType.purchase, amount=10.0
            )
        )
    session.commit()
    assert balance_of(session, xiaoming.id) == 30.0


# ── 安全网 2：课时 = 小时数 ────────────────────────


def test_扣课时按小时数扣不是固定扣一节课(session, lesson, students):
    """用户原话：「比如一个班级 48 小时，第一天上 2.5h 第二天上 3h，那就扣 5.5h。」"""
    assert lesson.hours == 2.5

    session.add(
        HourTransaction(
            student_id=students[0].id,
            type=TxnType.consume,
            amount=-lesson.hours,
            lesson_id=lesson.id,
        )
    )
    session.commit()
    assert balance_of(session, students[0].id) == -2.5


def test_买48小时上两节课后剩42_5小时(session, klass, teacher, students):
    """用户举的那个例子，逐字复现。"""
    xiaoming = students[0]
    session.add(
        HourTransaction(
            student_id=xiaoming.id, type=TxnType.purchase, amount=48.0
        )
    )
    session.commit()

    for day, hours in ((26, 2.5), (27, 3.0)):
        item = Lesson(
            class_id=klass.id,
            teacher_id=teacher.id,
            lesson_date=date(2026, 9, day),
            start_time=time(9, 0),
            hours=hours,
            rate=klass.rate,
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        session.add(
            HourTransaction(
                student_id=xiaoming.id,
                type=TxnType.consume,
                amount=-hours,
                lesson_id=item.id,
            )
        )
    session.commit()

    assert balance_of(session, xiaoming.id) == 42.5


# ── 安全网 3：费率快照 ─────────────────────────────


def test_改班级费率不会篡改历史课程的工资(session, klass, lesson):
    """历史工资表已经交给领导了，绝不能被后来的费率调整改掉。"""
    assert lesson.rate == 80.0

    klass.rate = 999.0
    session.add(klass)
    session.commit()

    session.refresh(lesson)
    assert lesson.rate == 80.0
    assert lesson.hours * lesson.rate == 200.0


# ── 安全网 4：密码与令牌 ───────────────────────────


def test_密码哈希可往返且不存明文():
    hashed = hash_password("hunter2")
    assert hashed != "hunter2"
    assert verify_password("hunter2", hashed)
    assert not verify_password("hunter3", hashed)


def test_超长密码不会让bcrypt报错():
    """bcrypt 只认前 72 字节，超长密码在旧版会静默截断、新版直接抛异常。"""
    long_password = "长" * 100
    hashed = hash_password(long_password)
    assert verify_password(long_password, hashed)


def test_校验损坏的哈希返回False不抛异常():
    assert not verify_password("whatever", "这不是一个合法的bcrypt哈希")


def test_jwt往返(teacher):
    token = create_access_token(teacher.id, teacher.role.value)
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == str(teacher.id)
    assert payload["role"] == "teacher"


def test_伪造的令牌解不开():
    assert decode_access_token("not.a.real.token") is None


def test_生成的密码不含易混字符():
    for _ in range(50):
        password = generate_password()
        assert len(password) == 10
        assert not set(password) & set("0O1lI")
