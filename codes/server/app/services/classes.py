"""班级的业务规则 —— 前缀校验、费率补全、在册关系、删除护栏。

单独放一层是为了能脱离 HTTP 直接测。

⚠️ 约定：**这里不 commit**。service 只做校验和「改内存里的对象」，
   落库由 router 统一 commit —— 跟 services/users.py 的分工一致。
"""

from datetime import date as Date

from fastapi import HTTPException, status
from sqlalchemy import delete as sa_delete
from sqlalchemy.sql.selectable import Subquery
from sqlmodel import Session, func, select

from app.core.class_rules import (
    ClassRuleError,
    resolve_class_fields,
    resolve_class_type,
)
from app.models import Class, ClassStudent, Lesson, LessonStatus, Student
from app.services.students import balance_subquery, get_active_students_or_400

_BAD_REQUEST = status.HTTP_400_BAD_REQUEST


def get_class_or_404(session: Session, class_id: int) -> Class:
    klass = session.get(Class, class_id)
    if klass is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="班级不存在",
        )
    return klass


def class_name_taken(
    session: Session, name: str, exclude_id: int | None = None
) -> bool:
    """班级名必须唯一。exclude_id 用于「改别的字段但没改班级名」。"""
    statement = select(Class).where(Class.name == name)
    if exclude_id is not None:
        statement = statement.where(Class.id != exclude_id)
    return session.exec(statement).first() is not None


def resolve_fields(
    name: str, class_type: str | None, rate: float | None
) -> tuple[str, float]:
    """把 core.class_rules 的校验错误转成 HTTP 400。

    校验逻辑本身是纯函数（能脱离 DB 测），这里只负责翻译成 HTTP。
    """
    try:
        return resolve_class_fields(name, class_type, rate)
    except ClassRuleError as exc:
        raise HTTPException(status_code=_BAD_REQUEST, detail=str(exc)) from exc


def resolve_type(name: str, class_type: str | None) -> str:
    """PATCH 用：只解析班级类型，不动费率。错误同样转 400。"""
    try:
        return resolve_class_type(name, class_type)
    except ClassRuleError as exc:
        raise HTTPException(status_code=_BAD_REQUEST, detail=str(exc)) from exc


def assert_rate_valid(rate: float) -> None:
    if rate <= 0:
        raise HTTPException(status_code=_BAD_REQUEST, detail="费率必须大于 0")


def active_member_count(session: Session, class_id: int) -> int:
    """当前在册人数（`left_on IS NULL`）。已退班的不算。"""
    return session.exec(
        select(func.count())
        .select_from(ClassStudent)
        .where(ClassStudent.class_id == class_id, ClassStudent.left_on.is_(None))
    ).one()


def lesson_count(session: Session, class_id: int) -> int:
    """该班有多少节课 —— **任意状态都算**。

    删除护栏用这个而不是 `total_completed_hours`：只要排过课就不许删班级，
    否则那些课就成了孤儿，工资表也追溯不回去。
    """
    return session.exec(
        select(func.count()).select_from(Lesson).where(Lesson.class_id == class_id)
    ).one()


def total_completed_hours(session: Session, class_id: int) -> float:
    """该班累计已上课时（只算 completed）。

    本轮 lessons 表还是空的，所以恒为 0.0；形状先定死，等课程接口做出来自动有值。
    """
    return session.exec(
        select(func.coalesce(func.sum(Lesson.hours), 0.0)).where(
            Lesson.class_id == class_id,
            Lesson.status == LessonStatus.completed,
        )
    ).one()


def assert_class_deletable(session: Session, class_id: int) -> None:
    """删除护栏：排过课就不许删，只能停用。

    ⚠️ 注意班级和学生的 DELETE 语义**不一样**（见 docs/实施计划.md §5.3 / §5.4）：
    学生的 DELETE 是软删（`is_active=False`）；班级的 DELETE 是**真删**，
    「停用」走 `PATCH /classes/{id}` 把 `is_active` 置 false。

    排过课的班级真删了，那些课就成了孤儿，工资表再也追溯不回去。
    """
    if lesson_count(session, class_id) > 0:
        raise HTTPException(
            status_code=_BAD_REQUEST,
            detail="该班级已有课程记录，不能删除，只能停用",
        )


def delete_class(session: Session, klass: Class) -> None:
    """真删班级。不 commit，由 router 落库。

    ⚠️ 必须先删 `class_students` 的关联行：`db.py` 开了 `foreign_keys=ON`，
    直接删班级会撞外键约束。能走到这里说明该班没有任何课程记录，
    所以这些关联行没有历史价值（没有课要追溯当时谁在册）。
    """
    session.execute(sa_delete(ClassStudent).where(ClassStudent.class_id == klass.id))
    session.delete(klass)


def member_count_subquery() -> Subquery:
    """按 class_id 聚合出**在册**人数（`left_on IS NULL`，退班的不算）。

    ⚠️ 用这个子查询时外面必须 LEFT JOIN + coalesce，
    否则一个学生都没有的班会整个消失在列表里（应该显示 0 才对）。
    """
    return (
        select(
            ClassStudent.class_id,
            func.count().label("student_count"),
        )
        .where(ClassStudent.left_on.is_(None))
        .group_by(ClassStudent.class_id)
        .subquery()
    )


def list_classes(
    session: Session, is_active: bool | None = None
) -> list[tuple[Class, int]]:
    """班级列表 + 各自的在册人数。

    人数先用子查询一次聚合完再 JOIN（不是每个班查一次），没有 N+1。
    """
    members = member_count_subquery()
    statement = (
        select(Class, func.coalesce(members.c.student_count, 0))
        .outerjoin(members, members.c.class_id == Class.id)
        .order_by(Class.id)
    )
    if is_active is not None:
        statement = statement.where(Class.is_active == is_active)
    return [tuple(row) for row in session.exec(statement).all()]


def list_class_students(
    session: Session, class_id: int
) -> list[tuple[Student, ClassStudent, float]]:
    """在册学生 + 各自的关联行 + 各自的剩余课时。

    一个学生在一个班里只会有一行关联（`ix_cs_pair` 保证），所以这里 JOIN 余额
    子查询不会把行数放大。没有流水的学生走 `coalesce` 显示 0。
    """
    balance = balance_subquery()
    statement = (
        select(Student, ClassStudent, func.coalesce(balance.c.remaining_hours, 0.0))
        .join(ClassStudent, ClassStudent.student_id == Student.id)
        .outerjoin(balance, balance.c.student_id == Student.id)
        .where(ClassStudent.class_id == class_id, ClassStudent.left_on.is_(None))
        .order_by(Student.id)
    )
    return [tuple(row) for row in session.exec(statement).all()]


def add_students_to_class(
    session: Session,
    klass: Class,
    student_ids: list[int],
    joined_on: Date,
) -> list[ClassStudent]:
    """批量把学生加进班级。不 commit，由 router 落库。

    **全有或全无**：只要有一个 student_id 无效，一行都不写。
    部分成功会让调用方不知道该不该重试，而重试会重复建关系/重复充值。

    ⚠️ 最关键的一点：`ix_cs_pair` 是 (class_id, student_id) **全表唯一**。
    退班再入班**必须复用原来的行**（清掉 left_on），直接 INSERT 会撞唯一索引。
    """
    # 去重、校验存在且启用 —— 有一个无效就 400，一行都不写
    students = get_active_students_or_400(session, student_ids)
    ids = [student.id for student in students]

    existing = session.exec(
        select(ClassStudent).where(
            ClassStudent.class_id == klass.id,
            ClassStudent.student_id.in_(ids),
        )
    ).all()
    by_student_id = {row.student_id: row for row in existing}

    result: list[ClassStudent] = []
    for student_id in ids:
        row = by_student_id.get(student_id)
        if row is None:
            row = ClassStudent(
                class_id=klass.id, student_id=student_id, joined_on=joined_on
            )
            session.add(row)
        elif row.left_on is None:
            pass  # 已经在册，幂等跳过（不报错、不新建）
        else:
            # ★ 退班再入班：复用原行，绝不能新建
            row.left_on = None
            row.joined_on = joined_on
            session.add(row)
        result.append(row)
    return result


def remove_student_from_class(
    session: Session, klass: Class, student_id: int, left_on: Date
) -> ClassStudent:
    """软移出：只写 `left_on`，**物理行保留**。

    这一行是「历史在册关系」，完成课程事务还要按 `joined_on <= 上课日期 < left_on`
    回查当时谁在册。真删了历史就断了。
    """
    row = session.exec(
        select(ClassStudent).where(
            ClassStudent.class_id == klass.id,
            ClassStudent.student_id == student_id,
        )
    ).first()
    if row is None or row.left_on is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该学生不在这个班的在册名单里",
        )

    row.left_on = left_on
    session.add(row)
    return row
