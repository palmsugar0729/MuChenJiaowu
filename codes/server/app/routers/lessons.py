"""课程与考勤（实施计划 5.5）。

权限分两档：

| 操作 | 谁能做 |
|---|---|
| 排课 / 改课 / 取消 / 删除 | 管理员（已含超管） |
| 看课程、**完成上课**、提交考勤 | 登录即可，但**老师只能碰自己的课** |

老师的正常流程是「看今天自己的课 → 勾谁出勤谁请假 → 点一次完成」，
所以「完成上课」不能收归管理员（那样每节课都要管理员来点）；
但也不能让老师改别人的课，那道槛在 `services/lessons.assert_can_access`。
"""

from datetime import date as Date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.core.deps import get_current_user, require_admin
from app.db import get_session
from app.models import Lesson, User
from app.schemas import (
    AttendanceSubmit,
    CompleteRequest,
    LessonCreate,
    LessonDetailRead,
    LessonRead,
    LessonStudentRead,
    LessonUpdate,
)
from app.services import lessons as lesson_service

router = APIRouter(prefix="/lessons", tags=["课程"])


def _to_lesson_read(
    lesson: Lesson, class_name: str, teacher_name: str, class_type: str
) -> LessonRead:
    """Lesson 行 + JOIN 出来的两个名字和班型 → 响应模型。

    显式逐字段写，不用 model_validate(lesson)：后端那张表里有
    `created_by` / `updated_at`，而接口刻意不暴露它们（跟 ClassRead 一样），
    显式写可以保证「表里加了字段，接口不会悄悄跟着漏出去」。
    """
    return LessonRead(
        id=lesson.id,
        class_id=lesson.class_id,
        class_name=class_name,
        class_type=class_type,
        teacher_id=lesson.teacher_id,
        teacher_name=teacher_name,
        lesson_date=lesson.lesson_date,
        start_time=lesson.start_time,
        hours=lesson.hours,
        rate=lesson.rate,
        status=lesson.status,
        note=lesson.note,
        content=lesson.content,
        created_at=lesson.created_at,
    )


def _detail(session: Session, lesson: Lesson) -> LessonDetailRead:
    """详情 = 课程信息 + 名单 + 各自出勤状态 + 各自余额。"""
    class_name, teacher_name, class_type = lesson_service.lesson_names(
        session, lesson
    )
    return LessonDetailRead(
        **_to_lesson_read(
            lesson, class_name, teacher_name, class_type
        ).model_dump(),
        students=[
            LessonStudentRead(
                student_id=student.id,
                name=student.name,
                status=attendance_status,
                remaining_hours=remaining,
            )
            for student, attendance_status, remaining in lesson_service.lesson_roster(
                session, lesson
            )
        ],
    )


# ── 列表 / 排课 ────────────────────────────────────


@router.get("", response_model=list[LessonRead], summary="课程列表")
def list_lessons(
    date: Date | None = None,
    month: str | None = None,
    start: Date | None = None,
    end: Date | None = None,
    teacher_id: int | None = None,
    class_id: int | None = None,
    actor: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[LessonRead]:
    """三个日期参数是可叠加的过滤器，不是三选一。

    - `date=YYYY-MM-DD` 某天（日视图）
    - `month=YYYY-MM` 整月（月视图）
    - `start=` / `end=` 任意区间

    ⚠️ **老师恒看自己的课**：`teacher_id` 对老师直接忽略，
       否则老师传个别人的 id 就能翻遍全校课表。
    """
    rows = lesson_service.list_lessons(
        session,
        actor=actor,
        date=date,
        month=month,
        start=start,
        end=end,
        teacher_id=teacher_id,
        class_id=class_id,
    )
    return [
        _to_lesson_read(lesson, class_name, teacher_name, class_type)
        for lesson, class_name, teacher_name, class_type in rows
    ]


@router.post(
    "",
    response_model=LessonRead,
    status_code=status.HTTP_201_CREATED,
    summary="排课",
)
def create_lesson(
    payload: LessonCreate,
    actor: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> LessonRead:
    """排一节课。

    ★ **费率不由客户端决定**：服务端从 `classes.rate` 抄一份存进 `lessons.rate`
      （费率快照）。以后改班级费率，不会篡改这节课的历史工资。
    """
    lesson = lesson_service.create_lesson(session, payload, actor)
    session.commit()
    session.refresh(lesson)

    class_name, teacher_name, class_type = lesson_service.lesson_names(
        session, lesson
    )
    return _to_lesson_read(lesson, class_name, teacher_name, class_type)


# ── 详情 / 改 / 删 ─────────────────────────────────


@router.get("/{lesson_id}", response_model=LessonDetailRead, summary="课程详情")
def get_lesson(
    lesson_id: int,
    actor: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> LessonDetailRead:
    """课程信息 + 学生名单 + 各自出勤状态（None = 还没点名）+ 各自余额。"""
    lesson = lesson_service.get_lesson_or_404(session, lesson_id)
    lesson_service.assert_can_access(actor, lesson)
    return _detail(session, lesson)


@router.patch("/{lesson_id}", response_model=LessonRead, summary="改课")
def update_lesson(
    lesson_id: int,
    payload: LessonUpdate,
    _actor: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> LessonRead:
    """管理员直改，免审批（老师改期要走审批流，那是 Phase 5）。

    **只有「已排课」的课能改**：已完成的课改课时数，会让 `lessons.hours`
    和已经扣掉的流水对不上。要改就取消重排。
    """
    lesson = lesson_service.get_lesson_or_404(session, lesson_id)
    lesson_service.update_lesson(session, lesson, payload)
    session.commit()
    session.refresh(lesson)

    class_name, teacher_name, class_type = lesson_service.lesson_names(
        session, lesson
    )
    return _to_lesson_read(lesson, class_name, teacher_name, class_type)


@router.delete("/{lesson_id}", response_model=LessonRead, summary="删除课程")
def delete_lesson(
    lesson_id: int,
    _actor: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> LessonRead:
    """**真删**，只有没上过的课能删。上过的课只能取消（取消会把课时退回去）。"""
    lesson = lesson_service.get_lesson_or_404(session, lesson_id)

    # 先把要返回的内容取出来：lesson 删掉之后实例就取不出值了
    class_name, teacher_name, class_type = lesson_service.lesson_names(
        session, lesson
    )
    result = _to_lesson_read(lesson, class_name, teacher_name, class_type)

    lesson_service.delete_lesson(session, lesson)
    session.commit()
    return result


# ── ★ 完成 / 取消 / 考勤 ────────────────────────────


@router.post(
    "/{lesson_id}/complete",
    response_model=LessonDetailRead,
    summary="★ 完成上课（扣课时）",
)
def complete_lesson(
    lesson_id: int,
    payload: CompleteRequest,
    actor: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> LessonDetailRead:
    """★ **整个系统钱算得对不对，全看这一个事务。**

    `content`（上课内容）**必填**，`items` 可省（不带就是「全员出勤」）。

    几件事在一个事务里做完：写考勤、按班型算出该扣谁、给该扣的人写 consume
    流水（`amount = -lesson.hours`）、记下上课内容、把课程置为已完成。

    ⚠️ **谁被扣看班型**（2026-10-05 改的口径，见 `core/class_rules`）：
       1对1 **只有出勤的扣**；其他班型**开课就扣全员**，请假缺勤照样扣。

    ⚠️ **谁课时不够就整节课失败**（400，列出是谁），不会扣成负数。
    """
    lesson = lesson_service.get_lesson_or_404(session, lesson_id)
    lesson_service.assert_can_access(actor, lesson)

    lesson_service.complete_lesson(
        session, lesson, payload.items, payload.content, actor
    )

    try:
        session.commit()
    except IntegrityError as exc:
        # 走到这儿说明并发或重试：另一个请求已经给这节课写过 consume 流水，
        # 被 `uq_consume_once` 这个部分唯一索引挡下了。
        # 事务整体回滚 —— 刚写进去的考勤记录也一起没了，不会留下半截状态。
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该课程已完成，请刷新后重试",
        ) from exc

    session.refresh(lesson)
    return _detail(session, lesson)


@router.post(
    "/{lesson_id}/cancel", response_model=LessonDetailRead, summary="取消课程"
)
def cancel_lesson(
    lesson_id: int,
    _actor: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> LessonDetailRead:
    """取消课程 —— 唯一不扣课时的情况。

    已经上过才取消（事后发现不该上）的，会把扣掉的课时**原样退回**。
    考勤记录保留（「本来安排了，后来取消了」的痕迹）。
    """
    lesson = lesson_service.get_lesson_or_404(session, lesson_id)
    lesson_service.cancel_lesson(session, lesson)
    session.commit()
    session.refresh(lesson)
    return _detail(session, lesson)


@router.post(
    "/{lesson_id}/attendance",
    response_model=LessonDetailRead,
    summary="提交 / 修改考勤",
)
def submit_attendance(
    lesson_id: int,
    payload: AttendanceSubmit,
    actor: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> LessonDetailRead:
    """事后补改考勤（当时点错了 / 补一张假条）。

    主流程里考勤是跟着「完成上课」一起提交的，这个接口只对**已完成**的课有效。
    全有或全无：有一个学生不在名单里就 400，一条都不改。

    ★ **考勤一改，课时跟着重算**：1对1 从「出勤」改成「请假」会把那节课的
      课时退回去，改回来再扣一次。`content` 可省，给了就是顺手补改上课内容。
    """
    lesson = lesson_service.get_lesson_or_404(session, lesson_id)
    lesson_service.assert_can_access(actor, lesson)
    lesson_service.submit_attendance(
        session, lesson, payload.items, payload.content, actor
    )
    session.commit()
    session.refresh(lesson)
    return _detail(session, lesson)
