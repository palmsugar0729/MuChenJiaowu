/**
 * 班级相关接口。纯函数，零平台依赖 —— 移植 uniapp 时原样搬走。
 *
 * 路径对照后端 codes/server/app/routers/classes.py，前缀 /api 由 client 补。
 *
 * ⚠️ 两个容易踩的语义（后端就是这么定的，别在页面里猜）：
 *   - `deleteClass` 是**真删**，且该班排过课就会 400（只能改用停用）
 *   - `removeClassStudent` 是**软移出**，只写 left_on，行还留着
 */

import { buildQuery, request } from './client'

/**
 * 班级列表。每行带 `student_count`（在册人数）。
 * `isActive` 传 undefined = 全都要（含已停用）；传 true 只看在册的。
 */
export function listClasses(isActive) {
  return request(`/classes${buildQuery({ is_active: isActive })}`)
}

/** 班级名前缀规则 + 费率表。前端拿来做实时联动，后端仍会独立校验。 */
export function getClassRules() {
  return request('/classes/rules')
}

export function createClass(payload) {
  return request('/classes', { method: 'POST', body: payload })
}

/** 详情：基础信息 + 在册学生 + 累计已上课时 + has_lessons（能不能删）。 */
export function getClass(id) {
  return request(`/classes/${id}`)
}

/**
 * 改班级。没传的字段一律不动 —— 尤其是 `rate`：
 * 改 `class_type` **不会**顺手改费率，费率只在显式传了才变。
 */
export function updateClass(id, patch) {
  return request(`/classes/${id}`, { method: 'PATCH', body: patch })
}

/** 真删。排过课的班会 400，调用方要 catch 住把 detail 显示出来。 */
export function deleteClass(id) {
  return request(`/classes/${id}`, { method: 'DELETE' })
}

export function listClassStudents(id) {
  return request(`/classes/${id}/students`)
}

/** 批量入班。**全有或全无** —— 有一个 id 无效就整批 400，一行都不写。 */
export function addClassStudents(id, studentIds, joinedOn) {
  return request(`/classes/${id}/students`, {
    method: 'POST',
    body: { student_ids: studentIds, joined_on: joinedOn },
  })
}

/** 移出班级（软移出）。`leftOn` 不传后端按今天算。 */
export function removeClassStudent(classId, studentId, leftOn) {
  return request(
    `/classes/${classId}/students/${studentId}${buildQuery({ left_on: leftOn })}`,
    { method: 'DELETE' },
  )
}
