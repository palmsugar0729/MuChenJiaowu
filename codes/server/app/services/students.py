"""学生的业务规则 —— 余额口径、课时流水的护栏。

⚠️ 与 services/classes.py 相同的约定：**这里不 commit**，落库由 router 统一做。
"""

from sqlalchemy.sql.selectable import Subquery
from fastapi import HTTPException, status
from sqlmodel import Session, func, or_, select

from app.models import (
    Attendance,
    Class,
    ClassStudent,
    HourTransaction,
    Student,
    TxnType,
    User,
)

_BAD_REQUEST = status.HTTP_400_BAD_REQUEST

# 与 models.Student 的 ck_students_gender 保持一致。
# 这里先拦一道是为了给出中文 400，而不是让 DB 抛 IntegrityError 变成 500。
_GENDERS = ("男", "女", "")


def balance_subquery() -> Subquery:
    """按 student_id 聚合出剩余课时，供列表查询复用（避免 N+1）。

    余额 = 该学生**所有**流水求和（不按 type 过滤）—— 见 AGENTS.md
    「学生余额不存字段，一律由 hour_transactions 求和算出」。

    ⚠️ 用这个子查询时外面必须 `LEFT JOIN` + `coalesce`，
    否则**一条流水都没有的学生会整个消失**（应该显示 0 才对）。
    """
    return (
        select(
            HourTransaction.student_id,
            func.coalesce(func.sum(HourTransaction.amount), 0.0).label(
                "remaining_hours"
            ),
        )
        .group_by(HourTransaction.student_id)
        .subquery()
    )


def get_student_or_404(session: Session, student_id: int) -> Student:
    student = session.get(Student, student_id)
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="学生不存在",
        )
    return student


def get_active_students_or_400(
    session: Session, student_ids: list[int]
) -> list[Student]:
    """一次查全并校验，返回去重、按 id 排好序的学生。

    **有一个无效就 400，一个都不返回** —— 批量入班和批量充值都靠这个
    实现「全有或全无」。部分成功最坑：调用方不知道该不该重试，
    而重试会重复建关系、重复充值（钱的事，宁可全失败）。
    """
    ids = list(dict.fromkeys(student_ids))
    if not ids:
        raise HTTPException(status_code=_BAD_REQUEST, detail="请至少选择一名学生")

    found = session.exec(
        select(Student).where(Student.id.in_(ids), Student.is_active.is_(True))
    ).all()
    found_ids = {student.id for student in found}
    missing = [student_id for student_id in ids if student_id not in found_ids]
    if missing:
        raise HTTPException(
            status_code=_BAD_REQUEST,
            detail="这些学生不存在或已停用：" + "、".join(str(i) for i in missing),
        )
    return sorted(found, key=lambda student: student.id)


def get_balance(session: Session, student_id: int) -> float:
    """单个学生的剩余课时。与 tests/test_safety_nets.py 的 balance_of 同口径。"""
    return session.exec(
        select(func.coalesce(func.sum(HourTransaction.amount), 0.0)).where(
            HourTransaction.student_id == student_id
        )
    ).one()


def list_students(
    session: Session,
    q: str | None = None,
    class_id: int | None = None,
    is_active: bool | None = None,
) -> list[tuple[Student, float]]:
    """学生列表（带余额）。

    ⚠️ 这里**必须先聚合再 LEFT JOIN**，不能同时 JOIN class_students 和
    hour_transactions —— 那样行数会相乘，把 SUM 放大成错的钱数。
    按班级筛选走 `IN (子查询)`，不额外 JOIN。
    """
    balance = balance_subquery()
    statement = select(
        Student, func.coalesce(balance.c.remaining_hours, 0.0)
    ).outerjoin(balance, balance.c.student_id == Student.id)

    if class_id is not None:
        statement = statement.where(
            Student.id.in_(
                select(ClassStudent.student_id).where(
                    ClassStudent.class_id == class_id,
                    ClassStudent.left_on.is_(None),
                )
            )
        )
    if is_active is not None:
        statement = statement.where(Student.is_active.is_(is_active))
    if q and q.strip():
        like = f"%{q.strip()}%"
        statement = statement.where(
            or_(Student.name.like(like), func.coalesce(Student.phone, "").like(like))
        )

    return [tuple(row) for row in session.exec(statement.order_by(Student.id)).all()]


def list_student_classes(session: Session, student_id: int) -> list[Class]:
    """该学生当前在册的班级（已退班的不算）。"""
    statement = (
        select(Class)
        .join(ClassStudent, ClassStudent.class_id == Class.id)
        .where(
            ClassStudent.student_id == student_id,
            ClassStudent.left_on.is_(None),
        )
        .order_by(Class.id)
    )
    return list(session.exec(statement))


def attendance_stats(session: Session, student_id: int) -> dict[str, int]:
    """出勤 / 请假 / 缺勤的笔数。

    本轮 attendance 表还是空的，所以三个数恒为 0；形状先定死，
    等考勤接口做出来自动有值，前端不用跟着改。
    """
    stats = {"present": 0, "leave": 0, "absent": 0}
    rows = session.exec(
        select(Attendance.status, func.count())
        .where(Attendance.student_id == student_id)
        .group_by(Attendance.status)
    ).all()
    for attendance_status, count in rows:
        # 枚举落库是成员名，读回来可能还是枚举对象，两种都兜住
        key = getattr(attendance_status, "value", attendance_status)
        if key in stats:
            stats[key] = count
    return stats


def assert_gender_valid(gender: str) -> None:
    if gender not in _GENDERS:
        raise HTTPException(
            status_code=_BAD_REQUEST,
            detail="性别只能是「男」「女」或留空",
        )


def assert_manual_txn_valid(txn_type: TxnType, amount: float, note: str) -> None:
    """手工录入课时的护栏。

    ★ `consume` 一律拒绝：消耗流水只能由「完成课程」事务产生（下一轮做），
      而且它会撞上 `uq_consume_once` 这个防重复扣课时的部分唯一索引。
      手工入口放进来等于把安全网捅个洞。
    """
    if txn_type == TxnType.consume:
        raise HTTPException(
            status_code=_BAD_REQUEST,
            detail="系统不允许手工录入消耗流水，请通过「完成上课」扣除课时",
        )

    if txn_type == TxnType.purchase:
        if amount <= 0:
            raise HTTPException(
                status_code=_BAD_REQUEST, detail="充值金额必须大于 0"
            )
    elif txn_type == TxnType.adjust:
        if amount == 0:
            raise HTTPException(status_code=_BAD_REQUEST, detail="调整金额不能为 0")
        if not note or not note.strip():
            raise HTTPException(
                status_code=_BAD_REQUEST, detail="调整课时必须填写备注"
            )


def add_hours(
    session: Session,
    student: Student,
    txn_type: TxnType,
    amount: float,
    note: str,
    actor: User,
) -> HourTransaction:
    """写一条手工课时流水（充值 / 调整）。

    ⚠️ 余额**允许为负**：`adjust` 就是用来修正错账和退费的，负余额是合法账实。
    只记录，不拦截，后端不设地板。
    """
    assert_manual_txn_valid(txn_type, amount, note)

    txn = HourTransaction(
        student_id=student.id,
        type=txn_type,
        amount=amount,
        lesson_id=None,  # 手工流水都不是因课消耗（consume 已被上面拒掉）
        note=(note or "").strip(),
        created_by=actor.id,
    )
    session.add(txn)
    return txn


def list_transactions(session: Session, student_id: int) -> list[HourTransaction]:
    """流水明细，新的在前。"""
    statement = (
        select(HourTransaction)
        .where(HourTransaction.student_id == student_id)
        .order_by(HourTransaction.created_at.desc(), HourTransaction.id.desc())
    )
    return list(session.exec(statement))
