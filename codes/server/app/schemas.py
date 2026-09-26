"""请求 / 响应模型。数据库表定义在 models.py，这里只管进出接口的数据形状。"""

from datetime import datetime

from sqlmodel import SQLModel

from app.models import Role


# ── 认证 ──────────────────────────────────────────


class LoginRequest(SQLModel):
    phone: str
    password: str


class ChangePasswordRequest(SQLModel):
    old_password: str
    new_password: str


class UserRead(SQLModel):
    """给前端的用户信息，绝不包含 password_hash。"""

    id: int
    phone: str
    display_name: str
    role: Role
    is_active: bool
    must_change_password: bool
    created_at: datetime


class TokenResponse(SQLModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


# ── 账号管理 ──────────────────────────────────────


class UserCreate(SQLModel):
    phone: str
    display_name: str
    role: Role = Role.teacher


class UserUpdate(SQLModel):
    display_name: str | None = None
    phone: str | None = None
    is_active: bool | None = None


class UserCreatedResponse(SQLModel):
    """建号 / 重置密码的返回。

    initial_password 只在这里出现一次——系统不存明文，丢了只能重置。
    """

    user: UserRead
    initial_password: str
