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
 * 月历一行的表头，**周一开头**。
 *
 * ⚠️ 别拿上面的 `WEEKDAYS` 凑：那个是「周日」开头、还带个「周」字，
 *    跟月历格子要的「一 二 … 日」两者都不一样。
 *    这个顺序和 `monthGrid()` 的首格偏移是配套的，也和桌面版
 *    `config.WEEKDAY_NAMES` 一致 —— 改一个就得改两个。
 */
export const MONTH_WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日']

/**
 * `YYYY-MM` → 当月天数。闰年交给 `Date` 自己算。
 *
 * ⚠️ `new Date(y, m, 0)` 这三处**看起来全是 off-by-one，但合起来才是对的**：
 *    `m` 是 1-based 的月份，却直接当 JS 那个 0-based 的月份索引用；
 *    日再传 `0`，于是落到「第 m 月的第 0 天」= **第 m 月的最后一天**。
 *    `new Date(2028, 2, 0)` → 2028-02-29，`new Date(2026, 12, 0)` → 2026-12-31。
 *    **别「顺手修正」成 `new Date(y, m - 1, 0)`** —— 那会变成上个月末，正月里少一天。
 *
 * 入参空或非法返回 `0`（手输 URL、`<input type="month">` 被清空都会喂进空串）。
 */
export function monthDays(month) {
  const [y, m] = (month || '').split('-').map(Number)
  if (!y || !m) return 0
  return new Date(y, m, 0).getDate()
}

/**
 * `YYYY-MM` → 月历格子数组，**周一开头**，前后补 `null` 凑满整行。
 * 元素是 `{ iso: 'YYYY-MM-DD', day: 1 }` 或 `null`（空格子），长度是 7 的倍数。
 *
 * 只画当月，不补相邻月份的日期（少一层「点下去到底算哪天」的歧义）。
 * 入参非法返回 `[]`。
 */
export function monthGrid(month) {
  const last = monthDays(month)
  if (!last) return []

  const [y, m] = month.split('-').map(Number)
  // getDay() 是 0=周日；+6 取模就转成 周一→0 … 周日→6，跟 MONTH_WEEKDAYS 对齐
  const leading = (new Date(y, m - 1, 1).getDay() + 6) % 7

  const cells = Array(leading).fill(null)
  for (let day = 1; day <= last; day += 1) {
    cells.push({ iso: `${month}-${pad(day)}`, day })
  }
  while (cells.length % 7) cells.push(null)

  return cells
}

/**
 * 把 `YYYY-MM-DD` 的「几号」搬进另一个月，**超出新月天数就落到月末**。
 *
 * 翻月时用：10-31 点「上月」→ 9-30，而不是溢出成 10-01。
 * 入参非法时原样返回 `iso`。
 */
export function moveDayToMonth(iso, month) {
  const last = monthDays(month)
  if (!last) return iso

  const day = Number((iso || '').slice(8, 10)) || 1
  return `${month}-${pad(Math.min(day, last))}`
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
