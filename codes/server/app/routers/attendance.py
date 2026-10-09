"""计薪统计与工资表导出（实施计划 §5.6 / §4.6，Phase 4）。

口径：只算 `status='completed'` 的课；课时费 = `hours × lessons.rate`（**快照**），
绝不 JOIN `classes.rate`。汇总数字和导出的 xlsx 出自 `services/payroll.month_rows`
同一条查询，所以屏幕上看到多少、下载下来就是多少。

| 接口 | 权限 |
|---|---|
| `GET /attendance/my` | 登录，**恒是自己** |
| `GET /attendance/summary` | 管理员 |
| `GET /attendance/export` | 登录；老师**恒导自己**，管理员可导单人 / 全体 |

⚠️ `/attendance` 下的三个路径**全是静态段**，这个 router 里没有任何 `/{id}` 动态路由，
   所以不存在 `classes.py` 里「`/rules` 被 `/{class_id}` 抢走」那种遮蔽问题
   （那条是路由声明顺序导致的）。**将来若要加 `/attendance/{id}`，动态段必须写在静态段后面。**
"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session

from app.core.deps import get_current_user, require_admin
from app.db import get_session
from app.exporters import salary_excel
from app.models import Role, User
from app.schemas import (
    PayrollLessonItem,
    PayrollMyRead,
    PayrollSummaryRead,
    PayrollTeacherSummary,
)
from app.services import payroll as payroll_service

router = APIRouter(prefix="/attendance", tags=["计薪统计"])

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_BAD_REQUEST = status.HTTP_400_BAD_REQUEST
_NOT_FOUND = status.HTTP_404_NOT_FOUND


def _content_disposition(filename: str) -> str:
    """中文文件名必须走 RFC 5987。

    `filename=` 那份是给老客户端的 ASCII 兜底（中文会被吃掉），
    `filename*=UTF-8''…` 那份才是现代浏览器实际用的 —— 下载下来就是「梁筱_工资结算表.xlsx」。
    """
    return (
        "attachment; filename=\"salary.xlsx\"; "
        f"filename*=UTF-8''{quote(filename, safe='')}"
    )


def _get_user_or_404(session: Session, user_id: int) -> User:
    """按 id 取账号。

    ⚠️ **刻意不检查 `is_active`**（不同于 `services/lessons.get_active_teacher_or_400`）：
       已经停用的老师，**他那几个月的工资是欠着人家的**，必须还能导出来。
       停用只挡「登不进来」，不挡「查历史的账」。
    """
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=_NOT_FOUND, detail="账号不存在")
    return user


# ── 我的 ──────────────────────────────────────────


@router.get("/my", response_model=PayrollMyRead, summary="我的课时数与课时费")
def read_my_payroll(
    month: str,
    actor: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> PayrollMyRead:
    """我的计薪 + 逐节明细。

    ⚠️ 恒按 `actor.id` 取，**不看角色** —— 管理员自己带课也一样走这里
    （授课人不限角色，排课时可以指定给任何启用账号）。
       没带过课就是 0，不是 404。

    `month` 必填（`YYYY-MM`）。**故意不做「省略 = 当月」**：服务器时区若是 UTC，
       在月初 00:00~08:00 会把「这个月」算成上个月 —— 跟前端不能用
       `toISOString()` 取今天是同一类坑。月份由前端按本地时间算好传进来。
    """
    rows = payroll_service.month_rows(session, month=month, teacher_id=actor.id)
    total_hours, total_salary = payroll_service.totals(rows)
    return PayrollMyRead(
        teacher_id=actor.id,
        teacher_name=actor.display_name,
        month=month,
        total_hours=total_hours,
        total_salary=total_salary,
        lessons=[
            PayrollLessonItem(
                lesson_id=r.lesson_id,
                lesson_date=r.lesson_date,
                start_time=r.start_time,
                hours=r.hours,
                rate=r.rate,
                salary=r.salary,
                class_id=r.class_id,
                class_name=r.class_name,
                class_type=r.class_type,
                note=r.note,
            )
            for r in rows
        ],
    )


# ── 全体汇总 ──────────────────────────────────────


@router.get("/summary", response_model=PayrollSummaryRead, summary="所有老师的汇总")
def read_summary(
    month: str,
    _actor: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> PayrollSummaryRead:
    """当月每位老师的课时数与课时费。

    只列**当月有已完成课**的老师 —— 没上过课的不出现，导出的 sheet 名单与这份一致。
    """
    rows = payroll_service.month_rows(session, month=month)
    totals = payroll_service.teacher_totals(rows)
    total_hours, total_salary = payroll_service.totals(rows)
    return PayrollSummaryRead(
        month=month,
        teacher_count=len(totals),
        total_hours=total_hours,
        total_salary=total_salary,
        teachers=[
            PayrollTeacherSummary(
                teacher_id=t.teacher_id,
                teacher_name=t.teacher_name,
                lesson_count=t.lesson_count,
                total_hours=t.total_hours,
                total_salary=t.total_salary,
            )
            for t in totals
        ],
    )


# ── 导出 ──────────────────────────────────────────


@router.get(
    "/export",
    summary="下载工资结算表（.xlsx）",
    response_class=Response,
    responses={200: {"content": {XLSX_MEDIA_TYPE: {}}}},
)
def export_payroll(
    month: str,
    teacher_id: int | None = None,
    actor: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    """导出 xlsx。

    - 老师：**`teacher_id` 传什么都不认**，恒导自己（同 `list_lessons` 的做法）
    - 管理员：给了 `teacher_id` 导那一位（单人单表）；省略则导所有人（每人一个 sheet）
    - 当月没有已完成的课 → 400（对应桌面版「没有记录」那道护栏）
    """
    # ★ 老师在这里没有选择权
    scope = actor.id if actor.role == Role.teacher else teacher_id
    if scope is not None:
        _get_user_or_404(session, scope)

    rows = payroll_service.month_rows(session, month=month, teacher_id=scope)
    if not rows:
        raise HTTPException(
            status_code=_BAD_REQUEST, detail="该月份没有已完成的课程，无法导出"
        )

    sheets = payroll_service.to_sheets(rows)
    single = scope is not None
    content = salary_excel.build_bytes(sheets, single=single)

    if single:
        # 与桌面版 `f"{teacher}_工资结算表.xlsx"` 同形
        name = salary_excel.safe_filename(sheets[0].teacher_name)
        filename = f"{name}_工资结算表.xlsx"
    else:
        filename = f"工资结算表_{month}.xlsx"

    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": _content_disposition(filename)},
    )
