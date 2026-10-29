"""审批（实施计划 5.7）。

权限分两档：

| 操作 | 谁能做 |
|---|---|
| 撤回自己的申请 | **老师本人**（管理员提不了申请，自然也撤不了） |
| 看列表 / 通过 / 驳回 | 管理员（已含超管） |

⚠️ 老师那侧有 `GET /approvals/my`（2026-10-29 加回来）：课程详情页只带**最近一条**
   申请，老师提交过两次之后前一条就看不见了（用户报的）。所以「我的」页给一个入口，
   列自己提过的全部申请（任何状态、新的在前）——**只读**，不做别的操作。

⚠️ 静态路径（`/my`）**必须写在 `/{approval_id}` 前面**，否则会被当成 id 去解析
   （同 `classes.py` 里 `/rules` 的坑）。目前 `/my` 与动态段没有冲突，但顺序
   是这条规矩的一部分，新加静态段照着排。
"""

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.deps import get_current_user, require_admin, require_role
from app.db import get_session
from app.models import ApprovalStatus, Role, User
from app.schemas import ApprovalRead, ApprovalReject
from app.services import approvals as approval_service

router = APIRouter(prefix="/approvals", tags=["审批"])


@router.get("", response_model=list[ApprovalRead], summary="审批列表")
def list_approvals(
    # ⚠️ 形参只能叫 status_filter：叫 `status` 会在函数体里把 fastapi 的 `status`
    #    模块遮掉（这个文件里 `status` 一次都没用到，但下一个改这里的人多半要用）。
    #    对外的 query 参数名仍然是 `status`。
    status_filter: ApprovalStatus = Query(
        ApprovalStatus.pending, alias="status"
    ),
    _actor: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> list[ApprovalRead]:
    """管理员看审批。**缺省只看待办**，`?status=approved` 之类可以查历史。

    非法值（`?status=xxx`）由 FastAPI 直接 422，不用自己校验。
    """
    return approval_service.list_approvals(session, status_filter=status_filter)


@router.get(
    "/my", response_model=list[ApprovalRead], summary="我的改期申请"
)
def list_my_approvals(
    actor: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[ApprovalRead]:
    """老师看**自己提过的全部申请**（任何状态），新的在前。

    前端入口在「我的」页 —— 课程详情页只带最近一条，提交过两次之后前一条
    （比如撤回的那条）就看不见了。这里**只读**；撤回仍然在课程详情页做。

    管理员调用会拿到空列表（他没提过申请），不额外 403 —— 省得前端按角色分叉。
    """
    return approval_service.list_by_requester(session, actor.id)


@router.post(
    "/{approval_id}/withdraw",
    response_model=ApprovalRead,
    summary="撤回改期申请",
)
def withdraw_approval(
    approval_id: int,
    actor: User = Depends(require_role(Role.teacher)),
    session: Session = Depends(get_session),
) -> ApprovalRead:
    """老师撤回自己提的申请。撤完就能重新提，旧那条留痕（状态 withdrawn）。

    ⚠️ 管理员走不到这儿（403）：他的改期走 `PATCH /lessons/{id}`，直接生效、不产生待办。
    """
    approval = approval_service.get_approval_or_404(session, approval_id)
    approval_service.withdraw(session, approval, actor)
    session.commit()
    return approval_service.get_read(session, approval_id)


@router.post(
    "/{approval_id}/approve",
    response_model=ApprovalRead,
    summary="通过改期申请",
)
def approve_approval(
    approval_id: int,
    actor: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> ApprovalRead:
    """通过 → **课程的时间真的改了**，并记下是谁批的。

    ★ 通过之前会**再查一次课程状态**：申请挂着的期间课可能已被完成或取消。
      那种情况返回 **409**，而不是静默把一节已经扣过课时的课改到别的日期上。

    一个事务改两张表（`lessons` + `approvals`），只在这里 commit 一次。
    """
    approval = approval_service.get_approval_or_404(session, approval_id)
    approval_service.approve(session, approval, actor)
    session.commit()
    return approval_service.get_read(session, approval_id)


@router.post(
    "/{approval_id}/reject",
    response_model=ApprovalRead,
    summary="驳回改期申请",
)
def reject_approval(
    approval_id: int,
    payload: ApprovalReject | None = None,
    actor: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> ApprovalRead:
    """驳回 → **课的时间一动不动**。

    理由**选填**，连请求体都可以整个不发（`payload` 缺省 None）。
    空串 / 全空格一律存 `None`。
    """
    approval = approval_service.get_approval_or_404(session, approval_id)
    approval_service.reject(
        session, approval, payload.reason if payload else None, actor
    )
    session.commit()
    return approval_service.get_read(session, approval_id)
