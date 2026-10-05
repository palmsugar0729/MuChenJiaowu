/**
 * 日期工具。零平台依赖，可移植。
 *
 * ⚠️ **别用 `new Date().toISOString().slice(0, 10)` 取「今天」。**
 *    它给的是 **UTC** 日期，而中国是 UTC+8 —— 本地时间 00:00~08:00 这段时间
 *    取出来是**昨天**。入班日期、移出日期这类业务日期会整整差一天。
 *    下面这个 todayISO() 走的是本地年月日，才是对的。
 */

function pad(n) {
  return String(n).padStart(2, '0')
}

/** 本地日期，`YYYY-MM-DD`。给后端的 Date 字段用。 */
export function todayISO() {
  const d = new Date()
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/**
 * 后端的审计时间戳 → `YYYY-MM-DD HH:mm`（本地时间）。
 *
 * 后端存的是 UTC，序列化出来带 `Z` 后缀（如 `2026-10-05T03:43:31Z`），
 * `new Date()` 认得这个后缀，会自己换算到本地时区。
 */
export function formatDateTime(value) {
  if (!value) return ''

  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value // 解析不了就原样显示，别显示 NaN

  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}`
  )
}

/** 后端已经给 `YYYY-MM-DD` 的字段（joined_on 这类），原样用；空值给个占位。 */
export function formatDate(value) {
  return value || '—'
}
