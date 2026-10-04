"""账号管理的业务规则 —— 谁有权管谁，以及几条不能碰的护栏。

单独放一层是为了能脱离 HTTP 直接测。这些规则写错，轻则管理员把自己关在门外，
重则最后一个超管被停用、整个后台再也进不去。
"""

from fastapi import HTTPException, status
from sqlmodel import Session, func, select

from app.models import Role, User


def can_manage(actor: User, target_role: Role) -> bool:
    """能不能管某个角色的账号。

    老师号：admin 和 super_admin 都能管（这是日常活儿）
    管理员号（含超管）：只有 super_admin 能动（这条防的是管理员互相拆台）
    """
    if target_role == Role.teacher:
        return actor.role in (Role.admin, Role.super_admin)
    return actor.role == Role.super_admin


def assert_can_manage(actor: User, target_role: Role) -> None:
    if not can_manage(actor, target_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="没有权限管理该账号",
        )


def assert_not_self(actor: User, target: User, action: str) -> None:
    """不能停用/删除自己 —— 一时手滑就得找别人来救。"""
    if actor.id == target.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不能{action}自己",
        )


def assert_not_last_super_admin(session: Session, target: User) -> None:
    """不能把最后一个启用中的超管停掉 —— 停了就没人能进后台了。"""
    if target.role != Role.super_admin or not target.is_active:
        return
    if active_super_admin_count(session) <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="这是最后一个启用中的超级管理员，不能停用",
        )


def get_user_or_404(session: Session, user_id: int) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="账号不存在",
        )
    return user


def phone_taken(session: Session, phone: str, exclude_id: int | None = None) -> bool:
    """手机号是登录标识，必须唯一。exclude_id 用于「改自己的但没改手机号」。"""
    statement = select(User).where(User.phone == phone)
    if exclude_id is not None:
        statement = statement.where(User.id != exclude_id)
    return session.exec(statement).first() is not None


def active_super_admin_count(session: Session) -> int:
    return session.exec(
        select(func.count())
        .select_from(User)
        .where(User.role == Role.super_admin, User.is_active.is_(True))
    ).one()
