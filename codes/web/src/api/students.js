/**
 * 学生 + 课时流水接口。纯函数，零平台依赖 —— 移植 uniapp 时原样搬走。
 *
 * 路径对照后端 codes/server/app/routers/students.py。
 *
 * ⚠️ 语义提醒：
 *   - `deactivateStudent` 是**软删**（is_active=false），行和流水都留着 ——
 *     真删了余额就再也算不出来
 *   - 手工流水只允许 `purchase`（充值）和 `adjust`（调整），
 *     `consume` 一律 400：消耗只能由「完成上课」产生
 */

import { buildQuery, request } from './client'

/**
 * 学生列表。每行都带 `remaining_hours`（后端一次查完，没有 N+1）。
 *
 * @param {object} [opts]
 * @param {string} [opts.q]         姓名或手机号，模糊匹配
 * @param {number} [opts.classId]   只看某个班的**在册**学生（含已退班的不算）
 * @param {boolean} [opts.isActive] undefined = 全都要（含已停用）
 */
export function listStudents({ q, classId, isActive } = {}) {
  return request(
    `/students${buildQuery({ q, class_id: classId, is_active: isActive })}`,
  )
}

export function createStudent(payload) {
  return request('/students', { method: 'POST', body: payload })
}

/** 详情：基础信息 + 余额 + 所属班级 + 出勤统计。 */
export function getStudent(id) {
  return request(`/students/${id}`)
}

export function updateStudent(id, patch) {
  return request(`/students/${id}`, { method: 'PATCH', body: patch })
}

/** 软删（停用）。已经是停用状态会 400。 */
export function deactivateStudent(id) {
  return request(`/students/${id}`, { method: 'DELETE' })
}

/** 课时流水明细（倒序）+ 当前余额。 */
export function getStudentHours(id) {
  return request(`/students/${id}/hours`)
}

/**
 * 单笔充值 / 调整。
 * @param {object} payload
 * @param {'purchase'|'adjust'} payload.type
 * @param {number} payload.amount  purchase 必须 > 0；adjust 可正可负但不能为 0
 * @param {string} [payload.note]  adjust **必填**（后端会 400）
 */
export function addStudentHours(id, payload) {
  return request(`/students/${id}/hours`, { method: 'POST', body: payload })
}

/**
 * 批量充值 —— 典型用法是「给一个班的学生统一买课时」。
 * **全有或全无**：名单里有一个无效/已停用的学生，一条流水都不写。
 *
 * @param {object} payload
 * @param {number[]} payload.student_ids
 * @param {number} payload.amount 必须 > 0
 * @param {string} [payload.note]
 */
export function batchAddHours(payload) {
  return request('/students/hours/batch', { method: 'POST', body: payload })
}
