/**
 * 课程 + 考勤接口。纯函数，零平台依赖 —— 移植 uniapp 时原样搬走。
 *
 * 路径对照后端 codes/server/app/routers/lessons.py，前缀 /api 由 client 补。
 *
 * ⚠️ 四条容易踩的语义（后端就是这么定的，别在页面里猜）：
 *   - `createLesson` **不收 rate**：费率由后端从班级快照一份，传了也会被忽略
 *   - `completeLesson` 是**全系统唯一扣课时的入口**，考勤跟着它一起提交
 *   - `cancelLesson` 会把已经扣掉的课时**退回去**（只有完成过的课才需要退）
 *   - 老师的课表**恒是自己的**：传 `teacherId` 也不会翻到别人的课
 */

import { buildQuery, request } from './client'

/**
 * 课程列表。三个日期参数是可叠加的过滤器，不是三选一。
 *
 * @param {object} [opts]
 * @param {string} [opts.date]    `YYYY-MM-DD`，日视图用
 * @param {string} [opts.month]   `YYYY-MM`，月视图用
 * @param {string} [opts.start]   区间起（含）
 * @param {string} [opts.end]     区间止（含）
 * @param {number} [opts.teacherId] 老师传了等于没传（后端会忽略）
 * @param {number} [opts.classId]
 */
export function listLessons({ date, month, start, end, teacherId, classId } = {}) {
  return request(
    `/lessons${buildQuery({
      date,
      month,
      start,
      end,
      teacher_id: teacherId,
      class_id: classId,
    })}`,
  )
}

/** 详情：课程信息 + 学生名单 + 各自出勤状态（null = 还没点名）+ 各自余额。 */
export function getLesson(id) {
  return request(`/lessons/${id}`)
}

/**
 * 排课（管理员）。
 *
 * @param {object} payload
 * @param {number} payload.class_id
 * @param {number} payload.teacher_id
 * @param {string} payload.date        `YYYY-MM-DD`
 * @param {string} payload.start_time  `HH:MM:SS`（<input type="time"> 给的是 HH:MM，要补秒）
 * @param {number} [payload.hours]     默认 1，必须 > 0
 * @param {string} [payload.note]
 */
export function createLesson(payload) {
  return request('/lessons', { method: 'POST', body: payload })
}

/** 改课（管理员）。**只有「已排课」的课能改**，改不了班级和费率。 */
export function updateLesson(id, patch) {
  return request(`/lessons/${id}`, { method: 'PATCH', body: patch })
}

/** 真删（管理员）。只有没上过的课能删 —— 上过的只能取消。 */
export function deleteLesson(id) {
  return request(`/lessons/${id}`, { method: 'DELETE' })
}

/**
 * ★ 完成上课（本人老师 / 管理员）—— **唯一扣课时的入口**。
 *
 * 一个事务里做完：写考勤 → 按班型算出该扣谁 → 扣 `-hours` 课时 →
 * 记下上课内容 → 课程置为已完成。
 *
 * ⚠️ **谁被扣看班型**：1对1 / 1对2 **只有出勤的扣**；其他班型**开课就扣全员**，
 *    请假缺勤照样扣（见 `core/class_rules.charges_only_present`）。
 * ⚠️ **谁课时不够就整节课失败**（400，`detail` 里列出是谁），不会扣成负数。
 * ⚠️ `content`（上课内容）**必填** —— 后端没有默认值，漏传是 422。
 * ⚠️ 不带 `items` 就是「全员出勤」。重复调用会 409。
 *
 * @param {string} content 上课内容（这节课上到哪了），**必填**
 * @param {object[]} [items] `[{ student_id, status: 'present'|'leave'|'absent' }]`
 */
export function completeLesson(id, content, items = []) {
  return request(`/lessons/${id}/complete`, {
    method: 'POST',
    body: { content, items },
  })
}

/** 取消课程（管理员）。已经扣掉的课时会原样退回，考勤记录保留。 */
export function cancelLesson(id) {
  return request(`/lessons/${id}/cancel`, { method: 'POST' })
}

/**
 * 事后改考勤（本人老师 / 管理员）。**只对已完成的课有效**。
 *
 * ★ **考勤一改，课时跟着重算**：按出勤扣的班型（1对1 / 1对2）从「出勤」改成
 *   「请假」会把那节课的课时退回去，改回来再扣一次。补扣时余额不够同样整批 400。
 * **全有或全无**：有一个学生不在名单里就整批 400，一条都不改。
 *
 * @param {object[]} items
 * @param {string} [content] 顺手补改上课内容；不传就不动
 */
export function submitAttendance(id, items, content) {
  const body = { items }
  if (content !== undefined) body.content = content
  return request(`/lessons/${id}/attendance`, { method: 'POST', body })
}
