"""全部数据表定义 —— 唯一真相源。

设计要点（详见 docs/实施计划.md 第三节）：
- 三种「课时」概念分离，别混
- 学生课时余额不存字段，一律由 hour_transactions 求和算出
- lessons.rate 是费率快照，改班级费率不影响历史工资
"""

from datetime import date as Date
from datetime import datetime, timezone
from datetime import time as Time
from enum import Enum

from sqlalchemy import CheckConstraint, Index, text
from sqlmodel import Field, SQLModel, UTCDateTime

# 时间戳统一存 UTC（SQLModel 0.0.47 只支持这一种带时区的存法）。
# ⚠️ 注意区分：这里说的是 created_at / recorded_at 这类「审计时间戳」。
# 业务日期（lesson_date / joined_on）是独立的 Date 字段，与是否存 UTC 无关。
#
# 用法是 `Field(..., sa_type=UTCDateTime)`，注解仍写 datetime ——
# UTCDateTime 是 SQLAlchemy 类型，直接当注解用 pydantic 会报错。


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── 枚举 ──────────────────────────────────────────


class Role(str, Enum):
    super_admin = "super_admin"
    admin = "admin"
    teacher = "teacher"


class LessonStatus(str, Enum):
    scheduled = "scheduled"  # 已排课
    completed = "completed"  # 已上课（已扣课时）
    cancelled = "cancelled"  # 已取消（不扣课时）


class AttendanceStatus(str, Enum):
    present = "present"  # 出勤
    leave = "leave"  # 请假
    absent = "absent"  # 缺勤


class TxnType(str, Enum):
    purchase = "purchase"  # 购买
    consume = "consume"  # 消耗（负数）
    adjust = "adjust"  # 手动调整


class ApprovalStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    withdrawn = "withdrawn"


# ── 用户 ──────────────────────────────────────────


class User(SQLModel, table=True):
    """超管 / 管理员 / 老师。学生不在这张表里，学生永远不登录。"""

    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    phone: str = Field(unique=True, index=True, description="登录标识")
    display_name: str = Field(description="真实姓名")
    password_hash: str = Field(description="bcrypt，绝不存明文")
    role: Role = Field(default=Role.teacher, index=True)
    is_active: bool = Field(default=True, description="停用而非删除")
    must_change_password: bool = Field(default=True, description="首次登录强制改密")
    created_at: datetime = Field(default_factory=utcnow, sa_type=UTCDateTime)
    updated_at: datetime | None = Field(default=None, sa_type=UTCDateTime)


# ── 班级 ──────────────────────────────────────────


class Class(SQLModel, table=True):
    """班级。费率就是班级的属性，没有跨班级复用场景，故不单独建 rates 表。"""

    __tablename__ = "classes"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    class_type: str = Field(description="1对1 / 1对2 …（决定时薪档位）")
    rate: float = Field(description="当前时薪（元/时）")
    note: str = Field(default="")
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utcnow, sa_type=UTCDateTime)


# ── 学生 ──────────────────────────────────────────


class Student(SQLModel, table=True):
    """学生。注意：没有 remaining_hours 字段，余额由流水算出。"""

    __tablename__ = "students"
    __table_args__ = (
        CheckConstraint("gender IN ('男', '女', '')", name="ck_students_gender"),
    )

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    gender: str = Field(default="")
    is_adult: bool | None = Field(default=None, description="None=未知")
    phone: str | None = None
    note: str = Field(default="")
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utcnow, sa_type=UTCDateTime)


class ClassStudent(SQLModel, table=True):
    """班级-学生 多对多。学生可同时在多个班。"""

    __tablename__ = "class_students"
    __table_args__ = (
        Index("ix_cs_pair", "class_id", "student_id", unique=True),
        Index("ix_cs_class", "class_id"),
        Index("ix_cs_student", "student_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    class_id: int = Field(foreign_key="classes.id")
    student_id: int = Field(foreign_key="students.id")
    joined_on: Date = Field(description="加入日期")
    left_on: Date | None = Field(default=None, description="退出日期，None=在册")


# ── 课程 ──────────────────────────────────────────


class Lesson(SQLModel, table=True):
    """课程（排课）。是整个系统的数据源头。"""

    __tablename__ = "lessons"
    __table_args__ = (
        Index("ix_lessons_date", "lesson_date"),
        Index("ix_lessons_teacher_date", "teacher_id", "lesson_date"),
        Index("ix_lessons_class", "class_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    class_id: int = Field(foreign_key="classes.id")
    teacher_id: int = Field(foreign_key="users.id")
    lesson_date: Date = Field(description="上课日期")
    start_time: Time = Field(description="开始时间")
    hours: float = Field(default=1.0, description="课时数=小时数，支持 2.5 这种")
    rate: float = Field(
        description="★ 时薪快照。排课时抄一份班级费率，"
        "改班级费率绝不能篡改历史工资表"
    )
    status: LessonStatus = Field(default=LessonStatus.scheduled, index=True)
    note: str = Field(default="")
    created_by: int | None = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=utcnow, sa_type=UTCDateTime)
    updated_at: datetime | None = Field(default=None, sa_type=UTCDateTime)


class Attendance(SQLModel, table=True):
    """出勤记录。

    ⚠️ 只是记录「谁来了谁没来」，不影响扣课时。
    出勤/请假/缺勤三种都照样扣，只有课程取消才不扣。
    """

    __tablename__ = "attendance"
    __table_args__ = (Index("ix_att_pair", "lesson_id", "student_id", unique=True),)

    id: int | None = Field(default=None, primary_key=True)
    lesson_id: int = Field(foreign_key="lessons.id", ondelete="CASCADE")
    student_id: int = Field(foreign_key="students.id")
    status: AttendanceStatus = Field(default=AttendanceStatus.present)
    recorded_by: int | None = Field(default=None, foreign_key="users.id")
    recorded_at: datetime | None = Field(default=None, sa_type=UTCDateTime)


# ── 学生课时流水 ★ ─────────────────────────────────


class HourTransaction(SQLModel, table=True):
    """学生课时流水 —— 全系统最关键的一张表。

    学生所剩课时 = 该学生所有流水求和，不存冗余字段（涉及钱，必须可追溯）。
    系统里「课时」就是「小时数」，不存在两套换算。
    """

    __tablename__ = "hour_transactions"
    __table_args__ = (
        # ★★ 防重复扣课时的安全网：同一节课对同一学生只允许一条消耗流水。
        # 老师误点两次「完成上课」、或网络重试导致请求重发，第二次写入会被数据库直接拒绝。
        Index(
            "uq_consume_once",
            "lesson_id",
            "student_id",
            unique=True,
            sqlite_where=text("type = 'consume'"),
        ),
        Index("ix_ht_student", "student_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    student_id: int = Field(foreign_key="students.id")
    type: TxnType = Field(index=True)
    amount: float = Field(description="购买/调整为正，消耗为负")
    lesson_id: int | None = Field(
        default=None,
        foreign_key="lessons.id",
        description="因哪节课消耗；购买时为 None",
    )
    note: str = Field(default="")
    created_by: int | None = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=utcnow, sa_type=UTCDateTime)


# ── 审批 ──────────────────────────────────────────


class Approval(SQLModel, table=True):
    """改期审批。刻意保持轻——一个待办列表 + 通过/驳回两个按钮。

    价值是让管理员知情、能担责任，不是真的要卡流程。
    """

    __tablename__ = "approvals"

    id: int | None = Field(default=None, primary_key=True)
    type: str = Field(default="lesson_reschedule", description="目前只有改期")
    target_id: int = Field(description="lessons.id")
    payload: str = Field(description="JSON：新日期/时间/原因")
    status: ApprovalStatus = Field(default=ApprovalStatus.pending, index=True)
    requested_by: int = Field(foreign_key="users.id")
    requested_at: datetime = Field(default_factory=utcnow, sa_type=UTCDateTime)
    reviewed_by: int | None = Field(default=None, foreign_key="users.id")
    reviewed_at: datetime | None = Field(default=None, sa_type=UTCDateTime)
    reject_reason: str | None = None
