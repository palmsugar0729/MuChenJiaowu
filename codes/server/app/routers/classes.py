"""班级管理（实施计划 5.3）。

读接口登录即可（老师能看），写接口一律 `require_admin`（已含超管）。

⚠️ 语义提醒：**班级的 DELETE 是真删**，停用走 `PATCH is_active=false`。
   这跟学生的 DELETE（软删）**不一样**，见 services/classes.py 的注释。
"""

from datetime import date as Date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.core.class_rules import (
    CLASS_NAME_RULES,
    CLASS_RATES,
    DEFAULT_RATE,
    SMALL_CLASS_DEFAULT,
    SMALL_CLASS_PREFIX,
    SMALL_CLASS_TYPES,
)
from app.core.deps import get_current_user, require_admin
from app.db import get_session
from app.models import Class, ClassStudent, Student, User, utcnow
from app.schemas import (
    ClassCreate,
    ClassDetailRead,
    ClassListItem,
    ClassRead,
    ClassRulesRead,
    ClassStudentsAdd,
    ClassStudentRead,
    ClassUpdate,
)
from app.services import classes as class_service
from app.services import students as student_service

router = APIRouter(prefix="/classes", tags=["班级"])
_BAD_REQUEST = status.HTTP_400_BAD_REQUEST


def _student_row(
    student: Student, link: ClassStudent, remaining_hours: float
) -> ClassStudentRead:
    return ClassStudentRead(
        student_id=student.id,
        name=student.name,
        joined_on=link.joined_on,
        left_on=link.left_on,
        remaining_hours=remaining_hours,
    )


@router.get("", response_model=list[ClassListItem], summary="班级列表")
def list_classes(
    is_active: bool | None = None,
    _actor: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[ClassListItem]:
    """每行都带 `student_count`（在册人数，一次聚合算完，没有 N+1）。"""
    return [
        ClassListItem(
            **ClassRead.model_validate(klass).model_dump(),
            student_count=count,
        )
        for klass, count in class_service.list_classes(session, is_active)
    ]


@router.get("/rules", response_model=ClassRulesRead, summary="班级名前缀规则 + 费率表")
def get_class_rules(_actor: User = Depends(get_current_user)) -> ClassRulesRead:
    """给前端做「班级名 → 班级类型 → 费率」实时联动用。

    由后端出这一份是为了让规则**只有一处**，改费率不用动前端。
    前端拿它只是即时反馈，后端建班级时仍会独立校验。
    """
    return ClassRulesRead(
        class_name_rules=[list(pair) for pair in CLASS_NAME_RULES],
        small_prefix=SMALL_CLASS_PREFIX,
        small_types=list(SMALL_CLASS_TYPES),
        small_default=SMALL_CLASS_DEFAULT,
        rates=dict(CLASS_RATES),
        default_rate=DEFAULT_RATE,
    )


@router.post(
    "", response_model=ClassRead, status_code=status.HTTP_201_CREATED, summary="建班级"
)
def create_class(
    payload: ClassCreate,
    _actor: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> Class:
    """`class_type` 按班级名前缀推断、`rate` 按类型查费率表，两个都能省。"""
    name = payload.name.strip()
    class_type, rate = class_service.resolve_fields(
        name, payload.class_type, payload.rate
    )

    if class_service.class_name_taken(session, name):
        raise HTTPException(
            status_code=_BAD_REQUEST, detail=f"班级名「{name}」已存在"
        )

    klass = Class(
        name=name,
        class_type=class_type,
        rate=rate,
        note=payload.note.strip(),
    )
    session.add(klass)
    session.commit()
    session.refresh(klass)
    return klass


@router.get("/{class_id}", response_model=ClassDetailRead, summary="班级详情")
def get_class(
    class_id: int,
    _actor: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ClassDetailRead:
    klass = class_service.get_class_or_404(session, class_id)
    rows = class_service.list_class_students(session, class_id)

    return ClassDetailRead(
        **ClassRead.model_validate(klass).model_dump(),
        students=[_student_row(s, link, hours) for s, link, hours in rows],
        student_count=len(rows),  # 在册人数就是 rows 的条数，不必再查一次
        total_hours=class_service.total_completed_hours(session, class_id),
        has_lessons=class_service.lesson_count(session, class_id) > 0,
    )


@router.patch("/{class_id}", response_model=ClassRead, summary="改班级")
def update_class(
    class_id: int,
    payload: ClassUpdate,
    _actor: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> Class:
    klass = class_service.get_class_or_404(session, class_id)

    name = klass.name
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=_BAD_REQUEST, detail="班级名不能为空")
        if class_service.class_name_taken(session, name, exclude_id=klass.id):
            raise HTTPException(
                status_code=_BAD_REQUEST, detail=f"班级名「{name}」已存在"
            )

    # 改了名字但没显式给类型 → 让前缀规则重新推断（YDY/YDE 这种定死的前缀会强制对齐）
    if payload.class_type is not None:
        class_type_arg: str | None = payload.class_type
    elif payload.name is not None:
        class_type_arg = None
    else:
        class_type_arg = klass.class_type

    klass.name = name
    klass.class_type = class_service.resolve_type(name, class_type_arg)

    # ★ 费率**只在显式提供时才改**：改班级类型不会顺手改价。
    #   费率是钱，而且 lessons.rate 是快照——意外改价会悄无声息地影响将来的工资表。
    if payload.rate is not None:
        class_service.assert_rate_valid(payload.rate)
        klass.rate = payload.rate

    if payload.note is not None:
        klass.note = payload.note.strip()
    if payload.is_active is not None:
        klass.is_active = payload.is_active

    klass.updated_at = utcnow()
    session.add(klass)
    session.commit()
    session.refresh(klass)
    return klass


@router.delete("/{class_id}", response_model=ClassRead, summary="删班级")
def delete_class(
    class_id: int,
    _actor: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> Class:
    """**真删**。排过课的班级一律拒绝，提示改用停用。

    返回被删掉的班级数据（删完就不是 ORM 对象了，先把字段读出来）。
    """
    klass = class_service.get_class_or_404(session, class_id)
    class_service.assert_class_deletable(session, klass.id)

    snapshot = ClassRead.model_validate(klass)
    class_service.delete_class(session, klass)
    session.commit()
    return snapshot


@router.get(
    "/{class_id}/students",
    response_model=list[ClassStudentRead],
    summary="在册学生",
)
def list_class_students(
    class_id: int,
    _actor: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[ClassStudentRead]:
    class_service.get_class_or_404(session, class_id)
    rows = class_service.list_class_students(session, class_id)
    return [_student_row(s, link, hours) for s, link, hours in rows]


@router.post(
    "/{class_id}/students",
    response_model=list[ClassStudentRead],
    status_code=status.HTTP_201_CREATED,
    summary="批量加入班级",
)
def add_class_students(
    class_id: int,
    payload: ClassStudentsAdd,
    _actor: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> list[ClassStudentRead]:
    """全有或全无：只要有一个学生无效，一行都不写。

    返回该班**当前在册的全部学生**（不只是这次加进来的），前端拿去做列表刷新。
    """
    klass = class_service.get_class_or_404(session, class_id)
    class_service.add_students_to_class(
        session, klass, payload.student_ids, payload.joined_on
    )
    session.commit()

    rows = class_service.list_class_students(session, class_id)
    return [_student_row(s, link, hours) for s, link, hours in rows]


@router.delete(
    "/{class_id}/students/{student_id}",
    response_model=ClassStudentRead,
    summary="移出班级",
)
def remove_class_student(
    class_id: int,
    student_id: int,
    left_on: Date | None = None,
    _actor: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> ClassStudentRead:
    """软移出：只写 `left_on`，关联行保留（历史要追溯当时谁在册）。

    `left_on` 不传就按今天算。返回的是**被移出的那一行**，
    它的 `remaining_hours` 是学生真实的余额（跟退不退班无关）。
    """
    klass = class_service.get_class_or_404(session, class_id)
    link = class_service.remove_student_from_class(
        session, klass, student_id, left_on or Date.today()
    )
    session.commit()

    student = session.get(Student, student_id)
    return _student_row(student, link, student_service.get_balance(session, student_id))
