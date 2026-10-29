"""审批 —— 目前只有「老师申请改期」。

原始需求（`docs/2026-09-17-需求讨论记录-课程管理系统.md:116`）：

> 如果某节课既定时间有变化的话，可以修改时间，并提交管理员审批（任意一个管理员即可）。
> 如果管理员自己修改就直接通过。虽然这个审批只是走个流程，但是好歹让管理员知情也能负担责任吧。

所以**这里刻意做得很轻**：一条待办 + 通过 / 驳回两个按钮。管理员自己改期仍然走
`PATCH /lessons/{id}`，直接生效、不产生待办 —— 审批只拦老师这一侧。

⚠️ 与别的 service 相同的约定：**这里不 commit**。`approve()` 要同时改
   `lessons` 和 `approvals` 两张表，正因为不 commit，它们天然在同一个事务里 ——
   中途抛错整体回滚，不会出现「课改了、审批还挂着 pending」。

⚠️ `Approval.target_id` **不是声明外键**（见 `models.Approval`），所以：
   - 读模型一律 `outerjoin`，课被删了也要能出行（对 None 已兜底）
   - ★ 删课时必须手工清掉审批行 —— 见 `services/lessons.delete_lesson()`，
     SQLite 会复用被删掉的 rowid，悬空的审批可能挂到一节毫不相干的新课上
"""

import json
from datetime import date as Date
from datetime import time as Time

from fastapi import HTTPException, status
from sqlalchemy.orm import aliased
from sqlmodel import Session, select

from app.models import Approval, ApprovalStatus, Class, Lesson, User, utcnow
from app.schemas import ApprovalRead
from app.services.lessons import assert_scheduled

_BAD_REQUEST = status.HTTP_400_BAD_REQUEST
_FORBIDDEN = status.HTTP_403_FORBIDDEN
_NOT_FOUND = status.HTTP_404_NOT_FOUND
_CONFLICT = status.HTTP_409_CONFLICT
# payload 是我们自己写的，读不出来说明库里那条真的坏了。**不能静默吞掉** ——
# 吞掉会让管理员对着一份「空的」申请点通过，课被改了却看不出改了什么。
_INTERNAL = status.HTTP_500_INTERNAL_SERVER_ERROR

# 目前只有这一种。做成常量而不是散在各处的字面量，将来加「销假」之类好找。
TYPE_RESCHEDULE = "lesson_reschedule"


# ── payload ★ 只由本模块写、只由本模块读 ─────────────
# 存 JSON 文本而不是拆三列，是为了将来加别的审批类型时不用改表。


def dump_reschedule(new_date: Date, new_start_time: Time, reason: str) -> str:
    """存 `{"date": "YYYY-MM-DD", "start_time": "HH:MM:SS", "reason": "..."}`。

    `ensure_ascii=False`：中文原因直接存原文，`sqlite3` 里 `.schema` / `select`
    一眼看得懂，排查问题时不用先 `json.loads` 再解码。
    """
    return json.dumps(
        {
            "date": new_date.isoformat(),
            "start_time": new_start_time.isoformat(),
            "reason": reason,
        },
        ensure_ascii=False,
    )


def parse_reschedule(payload: str) -> tuple[Date, Time, str]:
    """`dump_reschedule` 的逆操作 → (新日期, 新时间, 理由)。

    解析失败 → **500**（不是 400）：请求没毛病，是库里那条数据坏了。
    """
    try:
        data = json.loads(payload)
        return (
            Date.fromisoformat(data["date"]),
            Time.fromisoformat(data["start_time"]),
            str(data.get("reason") or ""),
        )
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise HTTPException(
            status_code=_INTERNAL, detail="审批数据损坏，请联系管理员"
        ) from exc


# ── 查 ────────────────────────────────────────────


def get_approval_or_404(session: Session, approval_id: int) -> Approval:
    approval = session.get(Approval, approval_id)
    if approval is None:
        raise HTTPException(status_code=_NOT_FOUND, detail="审批记录不存在")
    return approval


def assert_pending(approval: Approval) -> None:
    """只有 pending 的申请能撤回 / 通过 / 驳回。

    409 而不是 400 —— 跟课程生命周期一致（「资源当前状态不允许这个操作」），
    ⚠️ **不要**照抄班级 / 学生那种「已经是停用状态」的 400。

    这是防连点的最后一道：管理员开了两个标签页，第一个点通过了，
    第二个再点就会撞上它，而不是把一节已经改过期的课又改一次。
    """
    if approval.status != ApprovalStatus.pending:
        raise HTTPException(
            status_code=_CONFLICT, detail="该申请已处理，请刷新后重试"
        )


def find_pending_for_lesson(session: Session, lesson_id: int) -> Approval | None:
    """这节课有没有还挂着的申请。用来挡住重复提交。"""
    return session.exec(
        select(Approval).where(
            Approval.target_id == lesson_id,
            Approval.type == TYPE_RESCHEDULE,
            Approval.status == ApprovalStatus.pending,
        )
    ).first()


# ── 写 ────────────────────────────────────────────


def create_reschedule(session: Session, lesson: Lesson, payload, actor: User) -> Approval:
    """老师提一条改期申请。★ **课程时间当场不动**，等管理员通过才改。

    老师只能给自己的课提 —— 那道槛在 router（`assert_can_access`），
    跟完成上课走的是同一个入口。
    """
    assert_scheduled(lesson, "申请改期")

    reason = (payload.reason or "").strip()
    if not reason:
        # 表单上必填是 422（字段缺失），这里是「填了一串空格」—— 前端 trim 过，
        # 但接口不能指望前端。没有理由的申请就只是盖个章，那这套审批白做了。
        raise HTTPException(status_code=_BAD_REQUEST, detail="请填写改期理由")

    if find_pending_for_lesson(session, lesson.id) is not None:
        # 400 而不是 409：这是「你这次请求不合法」（同一节课不能挂两条），
        # 不是「这条申请的状态不对」。提示里告诉老师下一步该干什么。
        raise HTTPException(
            status_code=_BAD_REQUEST,
            detail="该课程已有待审批的改期申请，请先撤回后再提交",
        )

    approval = Approval(
        type=TYPE_RESCHEDULE,
        target_id=lesson.id,
        payload=dump_reschedule(payload.date, payload.start_time, reason),
        status=ApprovalStatus.pending,
        requested_by=actor.id,
    )
    session.add(approval)
    return approval


def approve(session: Session, approval: Approval, actor: User) -> Lesson:
    """通过 → 把新课的时间落到课上，并留痕。

    ★ **这里是第二次 `assert_scheduled`**：审批挂着的这段时间里，
      这节课可能已经被完成（老师上完了）或取消（管理员取消了）。
      那种情况下再改它的日期，等于改一节已经扣过课时、工资表上已有记录的课。
      ⚠️ 「通过前课被完成 → 409」这条测试就是冲着这一行来的，别删。

    `hours` / `rate` / `class_id` / `teacher_id` 一概不碰 —— payload 里就没有它们。
    """
    assert_pending(approval)

    lesson = session.get(Lesson, approval.target_id)
    if lesson is None:
        # target_id 不是外键，课可能已经被真删了（带 pending 的课删掉时审批行会一并清掉，
        # 但历史数据 / 并发下仍可能撞上）。给 404 让人去驳回，别 500。
        raise HTTPException(
            status_code=_NOT_FOUND, detail="课程不存在，可能已被删除"
        )

    assert_scheduled(lesson, "改期")

    new_date, new_start_time, _reason = parse_reschedule(approval.payload)

    lesson.lesson_date = new_date
    lesson.start_time = new_start_time
    lesson.updated_at = utcnow()

    approval.status = ApprovalStatus.approved
    approval.reviewed_by = actor.id
    approval.reviewed_at = utcnow()

    session.add(lesson)
    session.add(approval)
    return lesson


def reject(session: Session, approval: Approval, reason: str | None, actor: User) -> None:
    """驳回 → **课的时间一动不动**，只记一笔。

    理由选填（用户 2026-10-10 定的）。空串 / 全空格一律存 `None` ——
    库里只有「有理由」和「没理由」两种，不用在显示时再判一次 `strip()`。
    """
    assert_pending(approval)

    approval.status = ApprovalStatus.rejected
    approval.reject_reason = (reason or "").strip() or None
    approval.reviewed_by = actor.id
    approval.reviewed_at = utcnow()
    session.add(approval)


def withdraw(session: Session, approval: Approval, actor: User) -> None:
    """老师撤回自己提的申请 —— 撤完就能重新提（旧那条留在库里，状态 withdrawn）。

    先判归属再判状态：别人的申请，不管什么状态都不该让他知道能不能撤。
    """
    if approval.requested_by != actor.id:
        raise HTTPException(
            status_code=_FORBIDDEN, detail="只能撤回自己提交的申请"
        )
    assert_pending(approval)

    approval.status = ApprovalStatus.withdrawn
    session.add(approval)


# ── 读模型 ─────────────────────────────────────────
# ★ **一条 JOIN 出全部**：班级名 / 老师名 / 申请人 / 审批人四个都要，
#   列表页二十来行，一行行再查四次就是 80 次查询。
#   ⚠️ 一律 `outerjoin`：`target_id` 不是声明外键，课被删了那行也得能出得来
#   （`ApprovalRead` 对缺失已兜底成 None / ""）。

_teacher = aliased(User)
_requester = aliased(User)
_reviewer = aliased(User)


def _read_statement():
    return (
        select(
            Approval.id,
            Approval.type,
            Approval.target_id,
            Approval.status,
            Approval.payload,
            Approval.requested_by,
            Approval.requested_at,
            Approval.reviewed_by,
            Approval.reviewed_at,
            Approval.reject_reason,
            Lesson.class_id,
            Lesson.lesson_date,
            Lesson.start_time,
            Class.name,
            Class.class_type,
            Lesson.teacher_id,
            _teacher.display_name,
            _requester.display_name,
            _reviewer.display_name,
        )
        # 显式点出主表：select() 的列来自四张表，不写 select_from 的话
        # SQLAlchemy 猜不出该从哪张表往外 JOIN。
        .select_from(Approval)
        .outerjoin(Lesson, Lesson.id == Approval.target_id)
        .outerjoin(Class, Class.id == Lesson.class_id)
        .outerjoin(_teacher, _teacher.id == Lesson.teacher_id)
        .outerjoin(_requester, _requester.id == Approval.requested_by)
        .outerjoin(_reviewer, _reviewer.id == Approval.reviewed_by)
    )


def _to_read(row) -> ApprovalRead:
    (
        approval_id, type_, target_id, approval_status, payload,
        requested_by, requested_at, reviewed_by, reviewed_at, reject_reason,
        class_id, lesson_date, lesson_start_time, class_name, class_type,
        teacher_id, teacher_name, requester_name, reviewer_name,
    ) = row

    # 解析失败会 500 —— 刻意不吞（见 parse_reschedule 的说明）。
    new_date, new_start_time, reason = parse_reschedule(payload)

    return ApprovalRead(
        id=approval_id,
        type=type_,
        target_id=target_id,
        status=approval_status,
        new_date=new_date,
        new_start_time=new_start_time,
        reason=reason,
        class_id=class_id,
        class_name=class_name or "",
        class_type=class_type or "",
        teacher_id=teacher_id,
        teacher_name=teacher_name or "",
        lesson_date=lesson_date,
        lesson_start_time=lesson_start_time,
        requested_by=requested_by,
        requested_by_name=requester_name or "",
        requested_at=requested_at,
        reviewed_by=reviewed_by,
        reviewed_by_name=reviewer_name,
        reviewed_at=reviewed_at,
        reject_reason=reject_reason,
    )


def list_approvals(
    session: Session,
    *,
    status_filter: ApprovalStatus = ApprovalStatus.pending,
) -> list[ApprovalRead]:
    """某状态的审批列表。

    ⚠️ 排序按 **id 升序**（先提的排前面）而不是时间倒序：这是一份**待办**，
       老的申请不该被新申请压到屏幕外面去 —— 那正是最该先处理的那条。
       （id 单调递增，同一秒提交的两条也有确定顺序。）
    """
    statement = (
        _read_statement()
        .where(Approval.status == status_filter)
        .order_by(Approval.id)
    )
    return [_to_read(row) for row in session.exec(statement).all()]


def list_by_requester(session: Session, user_id: int) -> list[ApprovalRead]:
    """某个老师提过的**全部**申请（任何状态），新的在前。

    「我的」页那个入口用它。课程详情页只带**最近一条** —— 提交过两次之后，
    前一条（比如被撤回的那条）就看不见了（用户 2026-10-29 报的）。
    数据一直在库里，这里只是给它一个能列出来的地方。

    ⚠️ 按 **`id desc`**（新的在上），跟 `latest_for_lesson` 一个口径。
       只有管理员那份**待办**才是升序 —— 老申请得先处理。
    """
    statement = (
        _read_statement()
        .where(Approval.requested_by == user_id)
        .order_by(Approval.id.desc())
    )
    return [_to_read(row) for row in session.exec(statement).all()]


def get_read(session: Session, approval_id: int) -> ApprovalRead:
    """按 id 回读一条。写接口 commit 之后用它构造返回值。"""
    row = session.exec(
        _read_statement().where(Approval.id == approval_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=_NOT_FOUND, detail="审批记录不存在")
    return _to_read(row)


def latest_for_lesson(session: Session, lesson_id: int) -> ApprovalRead | None:
    """这节课**最近一条**审批，**任何状态**（没有就是 None）。

    课程详情页把它带出去：老师据此显示「待审批 → 新时间」+ 撤回按钮，
    管理员据此看出这节课的时间为什么变过（已通过 / 已驳回 / 已撤回）。

    ⚠️ 按 **`id desc`** 取，不是 `requested_at`。id 单调递增，
       同一秒内提交的两条也能定出胜负；时间戳撞车就说不清了。
    """
    row = session.exec(
        _read_statement()
        .where(Approval.target_id == lesson_id)
        .order_by(Approval.id.desc())
        .limit(1)
    ).first()
    return _to_read(row) if row is not None else None
