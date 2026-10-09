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

/**
 * `YYYY-MM-DD` 加减天数，结果仍是 `YYYY-MM-DD`。
 *
 * 用本地时间构造（`new Date(y, m-1, d)`）再 `setDate`：跨月跨年由它自己算，
 * 而且全程不碰 UTC —— 跟 todayISO() 一个道理。
 */
export function shiftDays(iso, days) {
  const [y, m, d] = iso.split('-').map(Number)
  const dt = new Date(y, m - 1, d)
  dt.setDate(dt.getDate() + days)
  return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}`
}

const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

/** `YYYY-MM-DD` → 「周三」。日视图的标题用。 */
export function weekdayLabel(iso) {
  if (!iso) return ''
  const [y, m, d] = iso.split('-').map(Number)
  return WEEKDAYS[new Date(y, m - 1, d).getDay()] || ''
}

/**
 * `YYYY-MM-DD` → `YYYY-MM`（本地）。
 *
 * 计薪接口的 `month` 只能这么取。⚠️ 别写 `new Date().toISOString().slice(0, 7)` ——
 * 那是 UTC，中国 UTC+8 在月初 00:00~08:00 会取到**上个月**，
 * 跟「取今天」是同一个坑。后端也因此**故意不做**「省略 month = 当月」。
 */
export function monthOf(iso) {
  return (iso || '').slice(0, 7)
}

/** `YYYY-MM` 加减月份，结果仍是 `YYYY-MM`。跨年交给 `Date` 自己算。 */
export function shiftMonths(month, n) {
  const [y, m] = month.split('-').map(Number)
  const d = new Date(y, m - 1 + n, 1)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`
}

/**
 * 后端的 `start_time` 是 `HH:MM:SS`，界面上只想要 `HH:MM`。
 *
 * ⚠️ 这是个**没有时区的纯时间**，别拿 `new Date()` 去转 —— 会被当成某个日期上的时刻。
 *    直接截字符串最安全。
 */
export function formatTime(value) {
  return (value || '').slice(0, 5)
}
