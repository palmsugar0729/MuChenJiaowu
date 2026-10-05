"""请求 / 响应模型。数据库表定义在 models.py，这里只管进出接口的数据形状。"""

from datetime import date, datetime

from pydantic import ConfigDict
from sqlmodel import SQLModel

from app.models import Role, TxnType


# ── 认证 ──────────────────────────────────────────


class LoginRequest(SQLModel):
    phone: str
    password: str


class ChangePasswordRequest(SQLModel):
    old_password: str
    new_password: str


class UserRead(SQLModel):
    """给前端的用户信息，绝不包含 password_hash。"""

    # 可以直接 UserRead.model_validate(某个 User 实例)
    model_config = ConfigDict(from_attributes=True)

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


# ── 通用 ──────────────────────────────────────────


class MessageResponse(SQLModel):
    """只回一句话、没有数据体的接口用。"""

    message: str


# ── 班级 ──────────────────────────────────────────
# 注意：Class 表里有 updated_at（审计用），但刻意不从接口暴露 —— 跟 UserRead 一样，
# 只出 created_at。将来要展示「最后修改于」再加。


class ClassRead(SQLModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    class_type: str
    rate: float
    note: str
    is_active: bool
    created_at: datetime


class ClassListItem(ClassRead):
    """列表里的一行 —— 比 ClassRead 多一个在册人数（聚合子查询算出来的）。

    单独一个模型而不是直接塞进 ClassRead：`create` / `patch` / `delete` 的返回值
    都是光秃秃的一行，没有人数可给（而且那三个接口也不需要它）。
    """

    student_count: int


class ClassCreate(SQLModel):
    name: str
    # 两个都可省：class_type 按班级名前缀推断，rate 按 class_type 查费率表。
    # 推断不出来会报 400 而不是猜一个 —— 见 core/class_rules.py。
    class_type: str | None = None
    rate: float | None = None
    note: str = ""


class ClassUpdate(SQLModel):
    name: str | None = None
    class_type: str | None = None
    rate: float | None = None
    note: str | None = None
    is_active: bool | None = None


class ClassRulesRead(SQLModel):
    """班级名前缀规则 + 费率表，给前端做实时联动用。

    前端拿这份只是**即时反馈**，后端仍会独立校验，两边不一致也不会写进脏数据。
    """

    class_name_rules: list[list[str]]
    small_prefix: str
    small_types: list[str]
    small_default: str
    rates: dict[str, float]
    default_rate: float


class ClassStudentRead(SQLModel):
    """班级在册学生的一行。"""

    student_id: int
    name: str
    joined_on: date
    left_on: date | None
    remaining_hours: float


class ClassDetailRead(ClassRead):
    students: list[ClassStudentRead]
    student_count: int
    # 本轮 lessons 表还是空的，所以恒为 0.0。
    # 形状现在就定死，等课程接口做出来自动有值，前端不用跟着改。
    total_hours: float
    # 排过课就不许删（见 services/classes.py 的删除护栏）。
    # 提前给前端，界面才能把删除按钮禁掉并说明原因，而不是让人点了才吃 400。
    has_lessons: bool


class ClassStudentsAdd(SQLModel):
    student_ids: list[int]
    joined_on: date


# ── 学生 ──────────────────────────────────────────


class StudentRead(SQLModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    gender: str
    is_adult: bool | None
    phone: str | None
    note: str
    is_active: bool
    created_at: datetime


class StudentListItem(StudentRead):
    remaining_hours: float


class StudentCreate(SQLModel):
    name: str
    gender: str = ""
    is_adult: bool | None = None
    phone: str | None = None
    note: str = ""


class StudentUpdate(SQLModel):
    name: str | None = None
    gender: str | None = None
    is_adult: bool | None = None
    phone: str | None = None
    note: str | None = None
    is_active: bool | None = None


class AttendanceStats(SQLModel):
    """出勤统计。本轮恒为 0，形状先定死（同 ClassDetailRead.total_hours）。"""

    present: int = 0
    leave: int = 0
    absent: int = 0


class StudentDetail(StudentRead):
    remaining_hours: float
    classes: list[ClassRead]
    attendance: AttendanceStats


# ── 课时流水 ──────────────────────────────────────


class HourTransactionRead(SQLModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    type: TxnType
    amount: float
    lesson_id: int | None
    note: str
    created_by: int | None
    created_at: datetime


class StudentHoursRead(SQLModel):
    remaining_hours: float
    transactions: list[HourTransactionRead]


class HoursCreate(SQLModel):
    """单笔充值 / 调整。`consume` 由 service 层拒绝 —— 见 services/students.py。"""

    type: TxnType
    amount: float
    note: str = ""


class HoursBatchCreate(SQLModel):
    """批量购买（典型用法：给一个班的学生统一充课时）。只支持 purchase。"""

    student_ids: list[int]
    amount: float
    note: str = ""
