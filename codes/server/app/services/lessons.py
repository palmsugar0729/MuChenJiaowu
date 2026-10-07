"""课程与考勤 —— ★ 完成课程事务，**全系统唯一扣课时的入口**。

⚠️ 与 services/classes.py 相同的约定：**这里不 commit**，落库由 router 统一做。
   所以「完成课程」那六步天然在同一个事务里 —— 中途任何一步抛错都整体回滚，
   不会出现「考勤写了、课时没扣」这种半截状态。

⚠️ 关于 docs/实施计划.md §4.1 写的 `BEGIN IMMEDIATE`：**刻意没有实现**。
   `session.get()` 一执行，SQLAlchemy 2.0 的 autobegin 就已经开了事务，
   此时再手动 BEGIN 会直接报「cannot start a transaction within a transaction」。
   而它想防的那件事（两个管理员同时点完成 → 扣两次）已经由 `uq_consume_once`
   从数据库层兜住了：第二个事务写 consume 时撞唯一索引 → IntegrityError →
   router 回滚并回 409。真正要写的代码是**在 router 里 catch IntegrityError**。
"""

from calendar import monthrange
from datetime import date as Date

from fastapi import HTTPException, status
from sqlalchemy import delete as sa_delete
from sqlmodel import Session, func, or_, select

from app.models import (
    Attendance,
    AttendanceStatus,
    Class,
    ClassStudent,
    HourTransaction,
    Lesson,
    LessonStatus,
    Role,
    Student,
    TxnType,
    User,
    utcnow,
)
from app.core.class_rules import charges_only_present
from app.services.classes import get_class_or_404
from app.services.students import balance_subquery, get_balance

_BAD_REQUEST = status.HTTP_400_BAD_REQUEST
_FORBIDDEN = status.HTTP_403_FORBIDDEN
_NOT_FOUND = status.HTTP_404_NOT_FOUND
# 课程生命周期冲突统一 409。注意这与班级 / 学生模块用 400 表示「已经是停用状态」
# 不同 —— 那些是「状态不对」，课程这边是「资源当前状态不允许这个操作」，语义上更贴 Conflict。
_CONFLICT = status.HTTP_409_CONFLICT


# ── 查询 ──────────────────────────────────────────


def get_lesson_or_404(session: Session, lesson_id: int) -> Lesson:
    lesson = session.get(Lesson, lesson_id)
    if lesson is None:
        raise HTTPException(status_code=_NOT_FOUND, detail="课程不存在")
    return lesson


def assert_can_access(actor: User, lesson: Lesson) -> None:
    """老师只能看 / 操作**自己的**课；管理员不受限。

    读和写用的是同一条规则，所以只有一个函数：老师翻不到别的老师的课，
    自然也改不了。管理员能排课、能取消，也就能看全部。
    """
    if actor.role == Role.teacher and lesson.teacher_id != actor.id:
        raise HTTPException(status_code=_FORBIDDEN, detail="只能查看和操作自己的课程")


def lesson_names(session: Session, lesson: Lesson) -> tuple[str, str, str]:
    """(班级名, 老师名, 班型)。列表走 JOIN，详情走这个 —— 两次主键查询，够用。

    `class_type` 是给前端用的：老师点「完成上课」之前得知道这节课**谁会被扣**，
    而那是按班型分的（1对1 只有出勤的扣，其他全员扣）。让界面自己写死一句
    两种口径都涵盖的废话，不如把班型给过去，由 `class_rules` 的口径决定显示什么。
    """
    klass = session.get(Class, lesson.class_id)
    teacher = session.get(User, lesson.teacher_id)
    return (
        klass.name if klass else "",
        teacher.display_name if teacher else "",
        klass.class_type if klass else "",
    )


def month_bounds(month: str) -> tuple[Date, Date]:
    """`YYYY-MM` → (月初, 月末)。格式不对就 400，别让它悄悄变成空结果。"""
    try:
        year_text, month_text = month.split("-")
        year, mon = int(year_text), int(month_text)
        first = Date(year, mon, 1)
    except (AttributeError, ValueError):
        raise HTTPException(
            status_code=_BAD_REQUEST, detail="month 参数格式应为 YYYY-MM"
        ) from None

    return first, Date(year, mon, monthrange(year, mon)[1])


def list_lessons(
    session: Session,
    *,
    actor: User,
    date: Date | None = None,
    month: str | None = None,
    start: Date | None = None,
    end: Date | None = None,
    teacher_id: int | None = None,
    class_id: int | None = None,
) -> list[tuple[Lesson, str, str, str]]:
    """课程列表，一次 JOIN 出班级名和老师名（避免每行再查两次）。

    ★ **老师恒看自己的课**：`teacher_id` 参数对老师直接忽略，
      不忽略的话老师传个别人的 id 就能翻遍全校课表。
    """
    statement = (
        select(Lesson, Class.name, User.display_name, Class.class_type)
        .join(Class, Class.id == Lesson.class_id)
        .join(User, User.id == Lesson.teacher_id)
    )

    if actor.role == Role.teacher:
        statement = statement.where(Lesson.teacher_id == actor.id)
    elif teacher_id is not None:
        statement = statement.where(Lesson.teacher_id == teacher_id)

    if class_id is not None:
        statement = statement.where(Lesson.class_id == class_id)

    # 三个日期条件是可叠加的过滤器，不是三选一 —— 叠加比「谁优先」更不容易出意外
    if date is not None:
        statement = statement.where(Lesson.lesson_date == date)
    if month:
        first, last = month_bounds(month)
        statement = statement.where(
            Lesson.lesson_date >= first, Lesson.lesson_date <= last
        )
    if start is not None:
        statement = statement.where(Lesson.lesson_date >= start)
    if end is not None:
        statement = statement.where(Lesson.lesson_date <= end)

    statement = statement.order_by(
        Lesson.lesson_date, Lesson.start_time, Lesson.id
    )
    return [tuple(row) for row in session.exec(statement).all()]


def roster_at(session: Session, lesson: Lesson) -> list[Student]:
    """**上课当天在册**的学生。

    ⚠️ 边界是「当天在册」而不是「现在在册」：`joined_on <= 上课日` 且
    `left_on IS NULL 或 left_on > 上课日`。之后才入班的不该被扣这节课的课时，
    上课前就退班了的一样不该。
    """
    statement = (
        select(Student)
        .join(ClassStudent, ClassStudent.student_id == Student.id)
        .where(
            ClassStudent.class_id == lesson.class_id,
            ClassStudent.joined_on <= lesson.lesson_date,
            or_(
                ClassStudent.left_on.is_(None),
                ClassStudent.left_on > lesson.lesson_date,
            ),
        )
        .order_by(Student.id)
    )
    return list(session.exec(statement))


def lesson_roster(
    session: Session, lesson: Lesson
) -> list[tuple[Student, AttendanceStatus | None, float]]:
    """详情页的学生名单：在册学生 + 各自出勤状态 + 各自剩余课时。

    `status` 为 None 表示**还没点名**（没上过的课就是这样），
    前端据此默认高亮「出勤」。
    """
    balance = balance_subquery()
    statement = (
        select(
            Student,
            Attendance.status,
            func.coalesce(balance.c.remaining_hours, 0.0),
        )
        .join(ClassStudent, ClassStudent.student_id == Student.id)
        .outerjoin(
            Attendance,
            (Attendance.lesson_id == lesson.id)
            & (Attendance.student_id == Student.id),
        )
        .outerjoin(balance, balance.c.student_id == Student.id)
        .where(
            ClassStudent.class_id == lesson.class_id,
            ClassStudent.joined_on <= lesson.lesson_date,
            or_(
                ClassStudent.left_on.is_(None),
                ClassStudent.left_on > lesson.lesson_date,
            ),
        )
        .order_by(Student.id)
    )
    # 一个学生在同一节课最多一条考勤（ix_att_pair 唯一），所以 LEFT JOIN 不会放大行数
    return [tuple(row) for row in session.exec(statement).all()]


# ── 排课 / 改课 ────────────────────────────────────


def assert_hours_valid(hours: float | None) -> None:
    if hours is None or hours <= 0:
        raise HTTPException(status_code=_BAD_REQUEST, detail="课时必须大于 0")


def get_active_teacher_or_400(session: Session, teacher_id: int) -> User:
    """任课老师必须存在且启用。

    不限制角色 —— 管理员自己带课的情况是有的，硬卡 `role == teacher` 会把
    超管本人排不进去（生产上正是这么用的）。
    """
    user = session.get(User, teacher_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=_BAD_REQUEST, detail="指定的老师不存在或已停用"
        )
    return user


def create_lesson(session: Session, payload, actor: User) -> Lesson:
    """排课。

    ★ `rate` **由服务端从班级快照**，payload 里根本没有这个字段 ——
      让客户端传费率等于任何人都能给自己开 999 元/时，工资表当场失真。
    """
    klass = get_class_or_404(session, payload.class_id)
    if not klass.is_active:
        raise HTTPException(
            status_code=_BAD_REQUEST, detail="该班级已停用，不能排课"
        )

    assert_hours_valid(payload.hours)
    teacher = get_active_teacher_or_400(session, payload.teacher_id)

    lesson = Lesson(
        class_id=klass.id,
        teacher_id=teacher.id,
        lesson_date=payload.date,
        start_time=payload.start_time,
        hours=payload.hours,
        rate=klass.rate,  # ★ 快照：以后改班级费率不影响这节课
        note=(payload.note or "").strip(),
        created_by=actor.id,
    )
    session.add(lesson)
    return lesson


def assert_scheduled(lesson: Lesson, action: str) -> None:
    """只有「已排课」的课能改 / 能删。

    ⚠️ 已完成的课改 `hours` 会让 `lessons.hours` 和已经写下的 consume 流水
    （金额是 -旧 hours）对不上，账就烂了。要改就取消重排。
    """
    if lesson.status != LessonStatus.scheduled:
        raise HTTPException(
            status_code=_CONFLICT, detail=f"只有「已排课」的课程能{action}"
        )


def update_lesson(session: Session, lesson: Lesson, payload) -> Lesson:
    """管理员直改，免审批。

    **不收 `rate`，也不允许改 `class_id`** —— 换班就是取消重排，
    否则「费率快照算谁的」就说不清了。
    """
    assert_scheduled(lesson, "修改")

    if payload.teacher_id is not None:
        lesson.teacher_id = get_active_teacher_or_400(
            session, payload.teacher_id
        ).id

    if payload.date is not None:
        lesson.lesson_date = payload.date
    if payload.start_time is not None:
        lesson.start_time = payload.start_time
    if payload.hours is not None:
        assert_hours_valid(payload.hours)
        lesson.hours = payload.hours
    if payload.note is not None:
        lesson.note = payload.note.strip()

    lesson.updated_at = utcnow()
    session.add(lesson)
    return lesson


def delete_lesson(session: Session, lesson: Lesson) -> None:
    """真删。只有没上过的课能删 —— 上过的只能取消（取消会把课时退回去）。

    排过但没上过的课不可能有 consume 流水（`scheduled` 这个状态就保证了），
    也不可能有考勤（改考勤要求先完成），所以这里删得干净。
    """
    assert_scheduled(lesson, "删除")

    session.execute(
        sa_delete(Attendance).where(Attendance.lesson_id == lesson.id)
    )
    session.delete(lesson)


# ── ★ 完成课程 ─────────────────────────────────────


def _resolve_attendance_items(
    items, allowed_ids: set[int]
) -> dict[int, AttendanceStatus]:
    """把请求里的 `items` 翻译成 `{student_id: status}`。**全有或全无**。

    有一个 student_id 不在名单里就 400，一个都不写 —— 部分成功会让调用方
    不知道该不该重试，而重试会重复扣课时（钱的事，宁可全失败）。
    """
    resolved: dict[int, AttendanceStatus] = {}
    unknown: list[int] = []

    for item in items or []:
        if item.student_id not in allowed_ids:
            unknown.append(item.student_id)
        else:
            resolved[item.student_id] = item.status

    if unknown:
        raise HTTPException(
            status_code=_BAD_REQUEST,
            detail="这些学生不在本节课的名单里："
            + "、".join(str(i) for i in dict.fromkeys(unknown)),
        )
    return resolved


def assert_content_present(content: str | None) -> str:
    """上课内容必填（用户 2026-10-05 定的）。strip 之后判，纯空格不算填。"""
    text = (content or "").strip()
    if not text:
        raise HTTPException(
            status_code=_BAD_REQUEST, detail="请填写上课内容（这节课上到哪里了）"
        )
    return text


def charged_student_ids(
    klass: Class,
    students: list[Student],
    statuses: dict[int, AttendanceStatus],
) -> set[int]:
    """★ 按班型决定这节课该扣谁。

    - **1对1**：只有出勤（`present`）的才扣。没来这节课就没上，收钱没道理。
    - **其他班型**（含认不出的自定义类型）：**全员**，跟来没来无关。
      请假也占着时段和老师，小班照收。

    ⚠️ 这是 2026-10-05 用户改的口径，**推翻了原来「三种状态都扣」那条**。
       规则本体在 `core/class_rules.charges_only_present`，这里只负责套用。
    """
    if charges_only_present(klass.class_type):
        return {
            s.id
            for s in students
            if statuses.get(s.id, AttendanceStatus.present)
            == AttendanceStatus.present
        }
    return {s.id for s in students}


def assert_balances_sufficient(
    session: Session,
    lesson: Lesson,
    charge_ids: set[int],
    students: list[Student],
) -> None:
    """★ 课时不够就**整节课失败**，把是谁列出来。

    用户 2026-10-05 选的：**不**允许扣成负数（原来那套「余额可以为负」只留给
    手工 `adjust` 纠错用）。课时是预交的学费，欠费了不该由系统默默兜着 ——
    老师看到提示后先充值再上课。

    ⚠️ 全有或全无，和系统里其他批量操作一个道理：部分成功会让老师不知道该不该
       重试，而重试会重复扣课时。
    """
    by_id = {s.id: s for s in students}
    short: list[str] = []

    for student_id in sorted(charge_ids):
        balance = get_balance(session, student_id)
        if balance < lesson.hours:
            student = by_id.get(student_id)
            name = student.name if student else f"#{student_id}"
            short.append(f"{name}（剩 {balance:g}，需要 {lesson.hours:g}）")

    if short:
        raise HTTPException(
            status_code=_BAD_REQUEST,
            detail="课时不足，无法完成上课：" + "、".join(short) + "。请先充值。",
        )


def consume_student_ids(session: Session, lesson_id: int) -> set[int]:
    """这节课**现在**挂着 consume 流水的人。"""
    return set(
        session.exec(
            select(HourTransaction.student_id).where(
                HourTransaction.lesson_id == lesson_id,
                HourTransaction.type == TxnType.consume,
            )
        ).all()
    )


def complete_lesson(session: Session, lesson: Lesson, items, content, actor: User) -> None:
    """★ 完成上课 —— 扣课时的唯一入口。

    一个事务里做完几件事（不 commit，由 router 落库）：

      1. 校验状态是 scheduled（否则 409，防重复点）
      2. 查上课当天在册的学生
      3. 记考勤（items 里给的用给的，没给的默认「出勤」）
      4. ★ 按班型算出该扣谁（1对1 只有出勤的扣，其他全员扣）
      5. ★ 课时不够就整节课失败，一个人都不写
      6. 该扣的每人写一条 consume 流水，amount = -lesson.hours
      7. 记下上课内容（必填）
    """
    if lesson.status != LessonStatus.scheduled:
        raise HTTPException(
            status_code=_CONFLICT, detail="该课程已完成或已取消，不能重复完成"
        )

    text = assert_content_present(content)

    klass = get_class_or_404(session, lesson.class_id)
    students = roster_at(session, lesson)
    statuses = {
        s.id: AttendanceStatus.present for s in students
    } | _resolve_attendance_items(items, {s.id for s in students})

    charge_ids = charged_student_ids(klass, students, statuses)
    assert_balances_sufficient(session, lesson, charge_ids, students)

    for student in students:
        session.add(
            Attendance(
                lesson_id=lesson.id,
                student_id=student.id,
                status=statuses[student.id],
                recorded_by=actor.id,
                recorded_at=utcnow(),
            )
        )
        if student.id in charge_ids:
            session.add(
                HourTransaction(
                    student_id=student.id,
                    type=TxnType.consume,
                    amount=-lesson.hours,  # ★ 课时就是小时数，不存在两套换算
                    lesson_id=lesson.id,
                    created_by=actor.id,
                )
            )

    lesson.content = text
    lesson.status = LessonStatus.completed
    lesson.updated_at = utcnow()
    session.add(lesson)


# ── 取消 ──────────────────────────────────────────


def cancel_lesson(session: Session, lesson: Lesson) -> None:
    """取消课程 —— 全系统唯一「不扣课时」的情况。

    已经完成过的课才取消（事后发现不该上），要把扣掉的课时**原样退回**，
    所以删掉这节课产生的 consume 流水。

    ⚠️ **考勤行刻意保留**：那是「本来安排了，后来取消了」的痕迹。
       删了就看不出这节课原本要给谁上。
    """
    if lesson.status == LessonStatus.cancelled:
        raise HTTPException(status_code=_CONFLICT, detail="该课程已经取消")

    session.execute(
        sa_delete(HourTransaction).where(
            HourTransaction.lesson_id == lesson.id,
            HourTransaction.type == TxnType.consume,
        )
    )

    lesson.status = LessonStatus.cancelled
    lesson.updated_at = utcnow()
    session.add(lesson)


# ── 事后改考勤 ─────────────────────────────────────


def submit_attendance(session: Session, lesson: Lesson, items, content, actor: User) -> None:
    """提交 / 修改考勤，**并把课时跟着重算**。

    正常流程里考勤是**跟着「完成上课」一起提交的**（老师勾完点一次，见
    `complete_lesson`）。这个接口是事后补改用的：当时点错了，
    或者补录一张假条。

    只允许改**已完成**的课：还没上过的课没得点名（先完成上课），
    已取消的课点名也没有意义。

    ★ 2026-10-05 用户定的：**考勤一改，课时跟着重算**。理由是 1对1 改成
      「只有出勤才扣」之后，如果事后把出勤改成请假却不退课时，老师点错一次
      就会静默多收学生的钱，而账面上看不出来。

    ⚠️ 做法是**只动差额**（该扣而没扣的补上、不该扣而扣了的删掉），
       不是「全删了重建」—— 重建会把原有流水的 `created_at` 抹掉，
       审计痕迹就没了。
    """
    if lesson.status != LessonStatus.completed:
        raise HTTPException(
            status_code=_CONFLICT,
            detail="只有已完成课程的考勤可以修改，请先完成上课",
        )

    if not items and content is None:
        raise HTTPException(
            status_code=_BAD_REQUEST, detail="请至少提交一名学生的考勤"
        )

    students = roster_at(session, lesson)
    allowed_ids = {s.id for s in students}
    statuses = _resolve_attendance_items(items, allowed_ids)

    existing = {
        row.student_id: row
        for row in session.exec(
            select(Attendance).where(Attendance.lesson_id == lesson.id)
        ).all()
    }

    for student_id, attendance_status in statuses.items():
        row = existing.get(student_id)
        if row is None:
            # 完成课程时给全员都写过，正常走不到这里；兜一下手动改库造成的缺口
            row = Attendance(lesson_id=lesson.id, student_id=student_id)
        row.status = attendance_status
        row.recorded_by = actor.id
        row.recorded_at = utcnow()
        session.add(row)
        existing[student_id] = row

    if content is not None:
        lesson.content = assert_content_present(content)

    # ── 按最终的考勤状态重算这一节课该扣谁 ──
    # 先铺一层「全员出勤」的底，再让库里的实际状态覆盖它，最后让本次提交覆盖
    final_status: dict[int, AttendanceStatus] = {
        s.id: AttendanceStatus.present for s in students
    }
    for student_id, row in existing.items():
        if student_id in allowed_ids:
            final_status[student_id] = row.status
    final_status |= statuses

    klass = get_class_or_404(session, lesson.class_id)
    should_charge = charged_student_ids(klass, students, final_status)
    charged_now = consume_student_ids(session, lesson.id)

    to_add = should_charge - charged_now
    to_remove = charged_now - should_charge

    # 补扣之前先查余额：退课时不用查（钱是往回升的），补扣才可能不够
    assert_balances_sufficient(session, lesson, to_add, students)

    if to_remove:
        session.execute(
            sa_delete(HourTransaction).where(
                HourTransaction.lesson_id == lesson.id,
                HourTransaction.type == TxnType.consume,
                HourTransaction.student_id.in_(to_remove),
            )
        )

    for student_id in sorted(to_add):
        session.add(
            HourTransaction(
                student_id=student_id,
                type=TxnType.consume,
                amount=-lesson.hours,
                lesson_id=lesson.id,
                created_by=actor.id,
            )
        )

    lesson.updated_at = utcnow()
    session.add(lesson)
