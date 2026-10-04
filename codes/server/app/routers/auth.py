"""认证与个人信息（实施计划 5.1）。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.core.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db import get_session
from app.models import User, utcnow
from app.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    MessageResponse,
    TokenResponse,
    UserRead,
    UserUpdate,
)
from app.services.users import phone_taken

router = APIRouter(tags=["认证"])

MIN_PASSWORD_LENGTH = 6


@router.post("/auth/login", response_model=TokenResponse, summary="登录")
def login(
    payload: LoginRequest,
    session: Session = Depends(get_session),
) -> TokenResponse:
    """手机号 + 密码换 token。

    返回里带 `must_change_password`，前端据此强制跳改密页 —— 后端不拦，
    因为「强制」是界面的事，拦在后端反而让前端没法知道该跳哪儿。
    """
    phone = payload.phone.strip()
    user = session.exec(select(User).where(User.phone == phone)).first()

    # 账号不存在和密码错误回同一句话，不给撞库的人做区分
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="手机号或密码不正确",
        )

    # 停用则要说清楚：不然当事人只会以为是自己密码记错了，反复试
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已停用，请联系管理员",
        )

    return TokenResponse(
        access_token=create_access_token(user.id, user.role.value),
        user=UserRead.model_validate(user),
    )


@router.post(
    "/auth/change-password",
    response_model=MessageResponse,
    summary="修改自己的密码",
)
def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MessageResponse:
    """首次登录被强制走这里。改完 `must_change_password` 自动清掉。"""
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="原密码不正确",
        )

    if len(payload.new_password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"新密码至少 {MIN_PASSWORD_LENGTH} 位",
        )

    # 初始密码是系统生成的，强制改密的意义就在于换成一个只有自己知道的
    if payload.new_password == payload.old_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="新密码不能和原密码相同",
        )

    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    user.updated_at = utcnow()
    session.add(user)
    session.commit()

    return MessageResponse(message="密码已修改")


@router.get("/users/me", response_model=UserRead, summary="当前登录用户")
def read_me(user: User = Depends(get_current_user)) -> User:
    return user


@router.patch("/users/me", response_model=UserRead, summary="改自己的信息")
def update_me(
    payload: UserUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> User:
    """只能改姓名和手机号。"""
    if payload.is_active is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="启用 / 停用请找管理员操作",
        )

    if payload.display_name is not None:
        name = payload.display_name.strip()
        if not name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="姓名不能为空"
            )
        user.display_name = name

    if payload.phone is not None:
        phone = payload.phone.strip()
        if not phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="手机号不能为空"
            )
        if phone_taken(session, phone, exclude_id=user.id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该手机号已被占用",
            )
        user.phone = phone

    user.updated_at = utcnow()
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
