"""请求 / 响应模型。数据库表定义在 models.py，这里只管进出接口的数据形状。"""

# ⚠️ `date` 必须起别名：`LessonCreate` / `LessonUpdate` 里有个**字段就叫 date**，
# 而 pydantic 求值注解时能看见类命名空间 —— 字段名会把类型名遮掉，
# 于是 `date | None` 被算成 `None | None`，类都建不起来。
# services/lessons.py 也是同样的写法。
from datetime import datetime, time
from datetime import date as Date

from pydantic import ConfigDict
from sqlmodel import SQLModel

from app.models import AttendanceStatus, LessonStatus, Role, TxnType


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


class ClassTabRead(SQLModel):
    """班级列表顶部的一张分类卡。

    `key` 进 URL query（ASCII），`label` 显示给人看（中文），
    `types` 是这张卡接受哪些 `class_type` —— **前端按 class_type 筛，不按班级名筛**。
    """

    key: str
    label: str
    types: list[str]


class ClassRulesRead(SQLModel):
    """**前端启动时取一次的参考数据**：班级名前缀规则 + 费率表 + 各种默认值。

    前端拿这份只是**即时反馈**，后端仍会独立校验，两边不一致也不会写进脏数据。
    （路径挂在 `/classes/rules` 下是历史原因，实际内容早就超出「班级规则」了，
    加字段时不用纠结这个前缀 —— 关键是**别让前端抄一份常量**。）
    """

    class_name_rules: list[list[str]]
    small_prefix: str
    small_types: list[str]
    small_default: str
    # 班级列表顶部的分类卡（总览那张由前端自己加，不在这儿）。
    # ★ 卡面上是「1对1 / 1对2 / 小班」这种**人话**，不是 YDY / XB 这种内部编码。
    class_tabs: list[ClassTabRead]
    rates: dict[str, float]
    default_rate: float
    # 班级类型 → 在册人数上限。不在表里的类型 = 不限制。
    # 前端拿它显示「在册 2/5 人」并在满员时提前禁用「加入学生」。
    capacities: dict[str, int]
    # 新建学生时自动送的课时数。前端拿它在表单上**提前说一声**，
    # 不然「怎么一建完就多出 48 课时」会变成客服问题。
    default_student_hours: float


class ClassStudentRead(SQLModel):
    """班级在册学生的一行。"""

    student_id: int
    name: str
    joined_on: Date
    left_on: Date | None
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
    joined_on: Date


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


# ── 课时流水 ──────────────────────────────────────
# ⚠️ 定义顺序有讲究：pydantic 在**建类的当下**就要解析注解，
#    所以被别的模型引用的类型必须排在使用者前面。
#    `HourTransactionRead` 放在 `StudentDetail` 下面曾经直接 ImportError。


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


class StudentDetail(StudentRead):
    remaining_hours: float
    classes: list[ClassRead]
    attendance: AttendanceStats
    # ⚠️ 这个字段曾经漏掉过：详情页读的是 `transactions`，而它当时只挂在
    #    `StudentHoursRead`（/students/{id}/hours）上 —— 于是详情页渲染时
    #    `undefined.length` 抛异常，Vue 丢掉整次更新，页面**冻在「加载中」**。
    #    接口返回 200，日志里什么都没有，只有浏览器控制台能看到。
    transactions: list[HourTransactionRead]


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


# ── 课程 ──────────────────────────────────────────
# ⚠️ `LessonRead` 刻意**不加** from_attributes：它比 Lesson 表多了 `class_name` /
# `teacher_name`，是 JOIN 出来的。由 router 从 `(Lesson, 班名, 师名)` 三元组显式构造 ——
# 跟 StudentListItem 拼 balance 的写法一样。


class LessonRead(SQLModel):
    id: int
    class_id: int
    class_name: str
    # 班型。前端拿它解释「这节课谁会被扣课时」——
    # 1对1 只有出勤的扣，其他班型开课就扣全员。**不是** course 的固有能力，
    # 是跟着班级走的属性，这里透出去只是省前端一次请求。
    class_type: str
    teacher_id: int
    teacher_name: str
    lesson_date: Date
    start_time: time
    hours: float
    rate: float
    status: LessonStatus
    note: str
    content: str
    created_at: datetime


class LessonStudentRead(SQLModel):
    """详情页名单的一行。

    `status` 为 None = 还没点名（没上过的课），前端据此默认勾「出勤」。
    """

    student_id: int
    name: str
    status: AttendanceStatus | None
    remaining_hours: float


class LessonDetailRead(LessonRead):
    students: list[LessonStudentRead]


class LessonCreate(SQLModel):
    """排课。

    ⚠️ **没有 `rate` 字段** —— 费率由服务端从 `classes.rate` 快照一份，
       让客户端传等于谁都能给自己开 999 元/时。

    `date` 是请求里的键名，落到 DB 的 `lesson_date`（实施计划 §5.5 定的，别改）。
    """

    class_id: int
    teacher_id: int
    date: Date
    start_time: time
    hours: float = 1.0
    note: str = ""


class LessonUpdate(SQLModel):
    """改课。同样**没有 `rate`**，也**不允许改 `class_id`** —— 换班就是取消重排。"""

    date: Date | None = None
    start_time: time | None = None
    hours: float | None = None
    note: str | None = None
    teacher_id: int | None = None


class AttendanceItem(SQLModel):
    student_id: int
    status: AttendanceStatus = AttendanceStatus.present


class AttendanceSubmit(SQLModel):
    """事后改考勤（只允许已完成的课）。全有或全无。

    `content` 可省：完成上课时已经写过了，这里只是允许顺手补改。
    给了就不能是空串（不能拿它把已写的内容擦掉）。
    """

    items: list[AttendanceItem]
    content: str | None = None


class CompleteRequest(SQLModel):
    """完成上课的请求体。

    `items` **可省**：不带就是「全员出勤」。老师的正常流程是勾完状态一次提交，
    所以带上 items 才是主用法；不带是给「一键完成」留的后路。

    ⚠️ `content`（上课内容）**必填**，用户 2026-10-05 明确要求：
       「老师操作考勤的时候加一个备注，写上课上到哪里了，**不是可选的**」。
       所以这里没有默认值 —— 漏传是 422，传空串是 400（strip 之后判）。
    """

    content: str
    items: list[AttendanceItem] = []


# ── 计薪统计 ──────────────────────────────────────
# 只算 `status='completed'` 的课；课时费 = hours × `lessons.rate`（**快照**），
# 绝不 JOIN `classes.rate` —— 改一次费率不该篡改历史工资表。
# 汇总数字与导出的 xlsx 出自同一条查询（见 `services/payroll.py`），口径不会分叉。


class PayrollLessonItem(SQLModel):
    """逐节明细的一行。老师下载之前先拿它对一遍，金额不对时有据可查。"""

    lesson_id: int
    lesson_date: Date
    start_time: time
    hours: float
    rate: float  # ★ 快照
    salary: float  # = round(hours * rate, 2)，**这一节**的课时费
    class_id: int
    class_name: str
    class_type: str
    note: str


class PayrollMyRead(SQLModel):
    """`GET /attendance/my` —— 我自己的。

    ⚠️ 老师的这个接口**恒被服务端压成 actor.id**，query 里根本没有 teacher_id。
    """

    teacher_id: int
    teacher_name: str
    month: str  # 回显 YYYY-MM，让前端确认取的是哪个月
    total_hours: float
    total_salary: float
    lessons: list[PayrollLessonItem]


class PayrollTeacherSummary(SQLModel):
    """汇总里的一位老师。"""

    teacher_id: int
    teacher_name: str
    lesson_count: int
    total_hours: float
    total_salary: float


class PayrollSummaryRead(SQLModel):
    """`GET /attendance/summary` —— 全体老师。

    **只列当月有已完成课的老师**：没上过课的人不出现在这里，
    导出的 sheet 集合也和这份名单完全一致。
    """

    month: str
    teacher_count: int
    total_hours: float
    total_salary: float
    teachers: list[PayrollTeacherSummary]
