/**
 * 计薪统计 + 工资表导出。纯函数，零平台依赖 —— 移植 uniapp 时原样搬走。
 *
 * 路径对照后端 `codes/server/app/routers/attendance.py`，前缀 /api 由 client 补。
 *
 * ⚠️ 三条别在页面里猜的语义：
 *   - `month` **必填**（`YYYY-MM`）。后端**故意不做**「省略 = 当月」：服务器时区若是 UTC，
 *     月初 00:00~08:00 会把「这个月」算成上个月。一律用 `monthOf(todayISO())` 按本地算。
 *   - `/my` **恒是自己**，管理员调也只看自己上了多少课 —— 它就是「我的工资」，不是汇总。
 *   - 金额一律来自 `lessons.rate`（排课时的快照），跟班级当前费率无关。
 */

import { buildQuery, request, requestBlob } from './client'

/** 我自己的：课时数 + 课时费 + 逐节明细（下载前先拿它对一遍）。 */
export function myPayroll(month) {
  return request(`/attendance/my${buildQuery({ month })}`)
}

/** 全体老师汇总（管理员）。**只列当月有已完成课的老师**，跟导出的 sheet 名单一致。 */
export function payrollSummary(month) {
  return request(`/attendance/summary${buildQuery({ month })}`)
}

/**
 * 下载工资结算表（.xlsx）→ `{ blob, filename }`，落盘见 `utils/download.js`。
 *
 * @param {object} opts
 * @param {string} opts.month      `YYYY-MM`
 * @param {number} [opts.teacherId] 管理员导指定的一位；**老师传了也不认**（恒导自己）。
 *                                  省略时：老师 → 自己的单表；管理员 → 所有人（每人一个 sheet）。
 * @returns {Promise<{ blob: Blob, filename: string }>}
 */
export function exportPayroll({ month, teacherId } = {}) {
  return requestBlob(`/attendance/export${buildQuery({ month, teacher_id: teacherId })}`)
}
