"""账号管理（实施计划 5.2）。

整个路由 admin 起步，**老师调这里一律 403** —— 这是 Phase 1 的验收标准之一。
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.core.deps import require_admin
from app.core.security import generate_password, hash_password
from app.db import get_session
from app.models import Role, User, utcnow
from app.schemas import UserCreate, UserCreatedResponse, UserRead, UserUpdate
from app.services.users import (
    assert_can_manage,
    assert_not_last_super_admin,
    assert_not_self,
    get_user_or_404,
    phone_taken,
)

router = APIRouter(prefix="/admin", tags=["账号管理"])


@router.get("/users", response_model=list[UserRead], summary="账号列表")
def list_users(
    role: Role | None = None,
    is_active: bool | None = None,
    _actor: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> list[User]:
    statement = select(User)
    if role is not None:
        statement = statement.where(User.role == role)
    if is_active is not None:
        statement = statement.where(User.is_active == is_active)
    return list(session.exec(statement.order_by(User.id)))


@router.post(
    "/users",
    response_model=UserCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="建账号",
)
def create_user(
    payload: UserCreate,
    actor: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> UserCreatedResponse:
    """建完返回一次性初始密码，抄给本人，他首次登录会被强制改掉。"""
    assert_can_manage(actor, payload.role)

    phone = payload.phone.strip()
    name = payload.display_name.strip()
    if not phone or not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="手机号和姓名都不能为空",
        )
    if phone_taken(session, phone):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"手机号 {phone} 已被占用",
        )

    initial_password = generate_password()
    user = User(
        phone=phone,
        display_name=name,
        password_hash=hash_password(initial_password),
        role=payload.role,
        must_change_password=True,  # 默认就是这个值，写出来是为了让人看见
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    return UserCreatedResponse(
        user=UserRead.model_validate(user),
        initial_password=initial_password,
    )


@router.patch("/users/{user_id}", response_model=UserRead, summary="改账号")
def update_user(
    user_id: int,
    payload: UserUpdate,
    actor: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> User:
    """改姓名 / 手机号 / 启用停用。

    **角色改不了** —— 想换角色就新建一个号，别改老号。
    历史记录存的是 `user.id`，改角色等于把过去的记录算到另一个身份头上。
    """
    target = get_user_or_404(session, user_id)
    assert_can_manage(actor, target.role)

    if payload.display_name is not None:
        name = payload.display_name.strip()
        if not name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="姓名不能为空"
            )
        target.display_name = name

    if payload.phone is not None:
        phone = payload.phone.strip()
        if not phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="手机号不能为空"
            )
        if phone_taken(session, phone, exclude_id=target.id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"手机号 {phone} 已被占用",
            )
        target.phone = phone

    if payload.is_active is not None:
        if not payload.is_active:
            assert_not_self(actor, target, "停用")
            assert_not_last_super_admin(session, target)
        target.is_active = payload.is_active

    target.updated_at = utcnow()
    session.add(target)
    session.commit()
    session.refresh(target)
    return target


@router.delete("/users/{user_id}", response_model=UserRead, summary="停用账号")
def deactivate_user(
    user_id: int,
    actor: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> User:
    """软删：只置 `is_active=False`，记录留在库里。

    账号会出现在课程的 `teacher_id`、审批的 `created_by` 里，
    真删了历史记录就成了孤儿，工资表也追溯不回去。
    """
    target = get_user_or_404(session, user_id)
    assert_can_manage(actor, target.role)
    assert_not_self(actor, target, "停用")
    assert_not_last_super_admin(session, target)

    if not target.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该账号已经是停用状态",
        )

    target.is_active = False
    target.updated_at = utcnow()
    session.add(target)
    session.commit()
    session.refresh(target)
    return target


@router.post(
    "/users/{user_id}/reset-password",
    response_model=UserCreatedResponse,
    summary="重置密码",
)
def reset_password(
    user_id: int,
    actor: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> UserCreatedResponse:
    """忘记密码时用。新密码同样是系统生成、只显示这一次。"""
    target = get_user_or_404(session, user_id)
    assert_can_manage(actor, target.role)

    new_password = generate_password()
    target.password_hash = hash_password(new_password)
    target.must_change_password = True  # 重置完还是得自己改一遍
    target.updated_at = utcnow()
    session.add(target)
    session.commit()
    session.refresh(target)

    return UserCreatedResponse(
        user=UserRead.model_validate(target),
        initial_password=new_password,
    )
