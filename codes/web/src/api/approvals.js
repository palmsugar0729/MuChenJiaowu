/**
 * 审批接口。纯函数，零平台依赖 —— 移植 uniapp 时原样搬走。
 *
 * 路径对照后端 `codes/server/app/routers/approvals.py`，前缀 /api 由 client 补。
 *
 * ⚠️ 三条别在页面里猜的语义：
 *   - **当下那条申请**就地挂在课程详情页的 `lesson.approval` 上（老师提申请时
 *     本来就在那一页）；**全部历史**走 `listMyApprovals()`（「我的」页那个入口）。
 *   - 是否 pending 决定一切：撤回 / 通过 / 驳回一条已处理的申请都是 **409**。
 *   - 通过**不会**把 `hours` / `rate` / 班级 / 老师一起改掉 —— 改期申请只带日期和时间。
 */

import { buildQuery, request } from './client'

/**
 * 我提过的**全部**改期申请（任何状态），新的在前。
 *
 * 后端 `GET /approvals/my`。老师只能看到自己的；管理员拿到空列表（他不提申请）。
 * 课程详情页只带最近一条，提交过两次之后前一条就看不见了 —— 这里是给它的去处。
 */
export function listMyApprovals() {
  return request('/approvals/my')
}

/**
 * 审批列表（管理员）。
 *
 * @param {string} [status] `pending`（缺省）/ `approved` / `rejected` / `withdrawn`
 */
export function listApprovals(status = 'pending') {
  return request(`/approvals${buildQuery({ status })}`)
}

/** 撤回（**只有本人老师**，管理员 403）。撤回后可以重新提，旧那条留痕。 */
export function withdrawApproval(id) {
  return request(`/approvals/${id}/withdraw`, { method: 'POST' })
}

/**
 * 通过（管理员）→ **课程的时间真的改了**，并记下是谁批的。
 *
 * ⚠️ 审批挂着的期间课可能已被完成或取消，那种情况返回 **409**
 *    （后端刻意不静默改一节已扣过课时的课）。
 */
export function approveApproval(id) {
  return request(`/approvals/${id}/approve`, { method: 'POST' })
}

/** 驳回（管理员）。`reason` **选填** —— 不传就是不解释。课的时间一动不动。 */
export function rejectApproval(id, reason) {
  const body = reason === undefined || reason === '' ? {} : { reason }
  return request(`/approvals/${id}/reject`, { method: 'POST', body })
}
