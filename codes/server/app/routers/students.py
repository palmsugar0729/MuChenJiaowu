"""学生管理 + 课时流水（实施计划 5.4）。

读接口登录即可，写接口一律 `require_admin`（已含超管）。

⚠️ **班级的 DELETE 是真删，学生的 DELETE 是软删**，别写混了：
   学生挂在 attendance.student_id 和 hour_transactions.student_id 上，
   真删了历史流水就成了孤儿，余额再也追溯不回去。
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.core.config import settings
from app.core.deps import get_current_user, require_admin
from app.db import get_session
from app.models import HourTransaction, Student, TxnType, User, utcnow
from app.schemas import (
    AttendanceStats,
    HourTransactionRead,
    HoursBatchCreate,
    HoursCreate,
    StudentCreate,
    StudentDetail,
    StudentHoursRead,
    StudentListItem,
    StudentRead,
    StudentUpdate,
)
from app.services import students as student_service

router = APIRouter(prefix="/students", tags=["学生"])
_BAD_REQUEST = status.HTTP_400_BAD_REQUEST


@router.get("", response_model=list[StudentListItem], summary="学生列表")
def list_students(
    q: str | None = None,
    class_id: int | None = None,
    is_active: bool | None = None,
    _actor: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[StudentListItem]:
    """`q` 同时匹配姓名和手机号。每行都带 `remaining_hours`（一次查询算出来，没有 N+1）。"""
    rows = student_service.list_students(session, q, class_id, is_active)
    return [
        StudentListItem(
            **StudentRead.model_validate(student).model_dump(),
            remaining_hours=remaining,
        )
        for student, remaining in rows
    ]


@router.post(
    "",
    response_model=StudentRead,
    status_code=status.HTTP_201_CREATED,
    summary="建学生",
)
def create_student(
    payload: StudentCreate,
    actor: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> Student:
    """建档。

    ★ **新生默认送 48 课时**（2026-10-05 用户定的），省掉「建完档再去充一次」
      这一步；续费才需要手动充值。

    ⚠️ 这 48 课时是**真写一条 `purchase` 流水**，不是给 `remaining_hours` 塞个
       初值 —— 余额是流水求和算出来的，塞初值等于账对不上，而且学生详情页的
       流水列表里会凭空少一笔。
    """
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=_BAD_REQUEST, detail="学生姓名不能为空")

    gender = (payload.gender or "").strip()
    student_service.assert_gender_valid(gender)

    student = Student(
        name=name,
        gender=gender,
        is_adult=payload.is_adult,
        phone=(payload.phone or "").strip() or None,
        note=payload.note.strip(),
    )
    session.add(student)
    # 流水要挂 student_id，得先把自增 id 拿到手（flush 不提交）
    session.flush()

    student_service.add_hours(
        session,
        student,
        TxnType.purchase,
        settings.default_student_hours,
        settings.default_student_hours_note,
        actor,
    )

    session.commit()
    session.refresh(student)
    return student


@router.post(
    "/hours/batch",
    response_model=list[HourTransactionRead],
    status_code=status.HTTP_201_CREATED,
    summary="批量充值",
)
def batch_add_hours(
    payload: HoursBatchCreate,
    actor: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> list:
    """给一批学生充同样多的课时（典型用法：整班统一买课时）。

    全有或全无：有一个学生无效就 400，一条流水都不写。

    ⚠️ 这条路由必须**声明在 `/{student_id}/hours` 之前**：
    `student_id: int` 匹配不上 "hours"，FastAPI 会直接回 422 而不是继续往下找。
    """
    if payload.amount <= 0:
        raise HTTPException(status_code=_BAD_REQUEST, detail="充值金额必须大于 0")

    students = student_service.get_active_students_or_400(session, payload.student_ids)
    transactions = [
        student_service.add_hours(
            session, student, TxnType.purchase, payload.amount, payload.note, actor
        )
        for student in students
    ]
    session.commit()
    for transaction in transactions:
        session.refresh(transaction)
    return transactions


@router.get("/{student_id}", response_model=StudentDetail, summary="学生详情")
def get_student(
    student_id: int,
    _actor: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> StudentDetail:
    """详情 = 基本信息 + 余额 + 所属班级 + 出勤统计。

    出勤统计本轮**恒为 0**（考勤还没做），但形状已经定死，前端不用跟着改。
    """
    student = student_service.get_student_or_404(session, student_id)
    return StudentDetail(
        **StudentRead.model_validate(student).model_dump(),
        remaining_hours=student_service.get_balance(session, student_id),
        classes=student_service.list_student_classes(session, student_id),
        attendance=AttendanceStats(
            **student_service.attendance_stats(session, student_id)
        ),
        transactions=student_service.list_transactions(session, student_id),
    )


@router.patch("/{student_id}", response_model=StudentRead, summary="改学生")
def update_student(
    student_id: int,
    payload: StudentUpdate,
    _actor: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> Student:
    student = student_service.get_student_or_404(session, student_id)

    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=_BAD_REQUEST, detail="学生姓名不能为空")
        student.name = name

    # ⚠️ 这三个字段**本身就可以是 null**（is_adult 未知、phone 没填、gender 未填），
    # 所以不能用 `is not None` 判断「用户到底传了没」——那样一旦设过值就再也清不掉，
    # 界面上把「是否成年」改回「未填」会**静默失败**。
    # model_fields_set 才分得清「没传这个字段」和「显式传了 null」。
    if "gender" in payload.model_fields_set:
        gender = (payload.gender or "").strip()
        student_service.assert_gender_valid(gender)
        student.gender = gender

    if "is_adult" in payload.model_fields_set:
        student.is_adult = payload.is_adult

    if "phone" in payload.model_fields_set:
        student.phone = (payload.phone or "").strip() or None

    if payload.note is not None:
        student.note = payload.note.strip()
    if payload.is_active is not None:
        student.is_active = payload.is_active

    student.updated_at = utcnow()
    session.add(student)
    session.commit()
    session.refresh(student)
    return student


@router.delete("/{student_id}", response_model=StudentRead, summary="停用学生")
def deactivate_student(
    student_id: int,
    _actor: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> Student:
    """**软删**：只置 `is_active=False`，记录和流水全留着。

    学生挂在 `hour_transactions.student_id` 上，真删了余额就再也算不出来。
    """
    student = student_service.get_student_or_404(session, student_id)
    if not student.is_active:
        raise HTTPException(
            status_code=_BAD_REQUEST, detail="该学生已经是停用状态"
        )

    student.is_active = False
    student.updated_at = utcnow()
    session.add(student)
    session.commit()
    session.refresh(student)
    return student


@router.get(
    "/{student_id}/hours", response_model=StudentHoursRead, summary="课时流水"
)
def get_student_hours(
    student_id: int,
    _actor: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> StudentHoursRead:
    """流水明细（新的在前）+ 当前余额。"""
    student_service.get_student_or_404(session, student_id)
    return StudentHoursRead(
        remaining_hours=student_service.get_balance(session, student_id),
        transactions=student_service.list_transactions(session, student_id),
    )


@router.post(
    "/{student_id}/hours",
    response_model=HourTransactionRead,
    status_code=status.HTTP_201_CREATED,
    summary="充值 / 调整课时",
)
def add_student_hours(
    student_id: int,
    payload: HoursCreate,
    actor: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> HourTransaction:
    """手工录一笔课时流水。

    - `purchase`：金额必须为正
    - `adjust`：可正可负、**必须填备注**（余额允许被调成负数，那通常是错账或退费）
    - `consume`：一律拒绝 —— 消耗只能由「完成上课」产生（下一轮做）
    """
    student = student_service.get_student_or_404(session, student_id)
    transaction = student_service.add_hours(
        session, student, payload.type, payload.amount, payload.note, actor
    )
    session.commit()
    session.refresh(transaction)
    return transaction
