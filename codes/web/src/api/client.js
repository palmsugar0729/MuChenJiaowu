/**
 * 网络层 —— 原生 fetch 封装。
 *
 * 这一层**不认识 Vue、不认识 store、更不认识 router**。它只认两个外部注入的回调
 * （tokenGetter / onUnauthorized），在 main.js 里接线。这样做的原因有两个：
 *   1. 避免 router → store → api → client → router 的循环依赖
 *   2. router 是 web 独有的，混进来会把这一层变成不可移植
 */

// 默认相对路径 /api：dev 走 Vite 代理，生产走 Nginx 反代，行为一致。
// 只有在把 H5 挂到别的域名、不走同源反代时，才需要 .env 里给 VITE_API_BASE。
const BASE_URL = import.meta.env.VITE_API_BASE || '/api'

export class ApiError extends Error {
  constructor(message, status = 0, data = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status // 0 表示请求根本没发出去（断网、后端没起）
    this.data = data
  }
}

let tokenGetter = () => ''
let onUnauthorized = null

export function setTokenGetter(fn) {
  tokenGetter = fn
}

export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn
}

/**
 * 把后端的错误体归一成一句人话。
 *
 * FastAPI 的 detail 有两种形态：
 *   - 业务错   -> 字符串，直接给用户看
 *   - 校验失败 -> 数组 [{msg, loc, ...}]，不处理的话页面上会渲染成 [object Object]
 */
function messageFrom(data, status) {
  const detail = data?.detail

  if (typeof detail === 'string') return detail

  if (Array.isArray(detail) && typeof detail[0]?.msg === 'string') {
    return detail[0].msg
  }

  if (status === 401) return '登录已过期，请重新登录'
  if (status === 403) return '没有权限执行该操作'
  return `请求失败（${status}）`
}

/**
 * 发一个请求。成功返回响应体（后端不包一层，直接就是数据）；
 * 失败一律抛 ApiError，页面统一 catch (e) { error.value = e.message }。
 */
export async function request(path, { method = 'GET', body, auth = true } = {}) {
  const headers = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  const token = auth ? tokenGetter() : ''
  if (token) headers.Authorization = `Bearer ${token}`

  let response
  try {
    response = await fetch(BASE_URL + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError('网络连接失败，请检查网络后重试', 0)
  }

  const text = await response.text()
  let data = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text // 后端理论上只回 JSON，兜底一下
    }
  }

  if (!response.ok) {
    // ⚠️ 判定条件必须是「带了 token 还被 401」。
    // 登录接口密码错也是 401，但它没带 token —— 若在这里无条件触发登出，
    // 用户输错一次密码就会被踢出登录态，非常难查。
    if (response.status === 401 && token) onUnauthorized?.()

    throw new ApiError(messageFrom(data, response.status), response.status, data)
  }

  return data
}

/**
 * 从 `Content-Disposition` 里把文件名捞出来。
 *
 * 后端两种都给了：`filename="salary.xlsx"` 是给老客户端的 ASCII 兜底（中文会被吃掉），
 * `filename*=UTF-8''%E6%A2%81...`（RFC 5987）才是实际用的那份。
 * ⚠️ 顺序不能反 —— 先认 `filename*`，解不出来才退回 `filename`，否则永远拿到那个英文占位名。
 * 同源读得到；跨域要在后端开 `expose_headers=["Content-Disposition"]`（main.py 已开）。
 */
function filenameFrom(headers) {
  const disposition = headers.get('Content-Disposition') || ''

  const extended = /filename\*=UTF-8''([^;]+)/i.exec(disposition)
  if (extended) {
    try {
      return decodeURIComponent(extended[1].trim())
    } catch {
      // 编码坏了就往下走，用 ASCII 那份兜底
    }
  }

  const quoted = /filename="([^"]+)"/i.exec(disposition)
  return quoted ? quoted[1] : ''
}

/**
 * 发一个「要文件」的请求 —— 目前只有导出工资表用。
 *
 * 跟 `request()` 的三处差别：不写 JSON 的 Accept、读 `response.blob()`、
 * 顺带把文件名捎回来。
 *
 * ⚠️ 失败时**仍然按 JSON 解析错误体**。后端出错回的是 `{"detail": "..."}`，
 *    不能因为这次要的是二进制就把人话丢掉 —— 否则「本月没有已完成的课程」
 *    会变成一个光秃秃的「请求失败（400）」，用户不知道该怎么办。
 *
 * ❗ 这一层**不碰 `document`**。它只把 Blob 交出去，落盘由 `utils/download.js` 干 ——
 *    uniapp 那边拿到 Blob/临时路径后是另一套保存 API。
 */
export async function requestBlob(path, { method = 'GET' } = {}) {
  const headers = {}
  const token = tokenGetter()
  if (token) headers.Authorization = `Bearer ${token}`

  let response
  try {
    response = await fetch(BASE_URL + path, { method, headers })
  } catch {
    throw new ApiError('网络连接失败，请检查网络后重试', 0)
  }

  if (!response.ok) {
    // 判定条件同 request()：登录失败的 401 没带 token，不能拿它踢人
    if (response.status === 401 && token) onUnauthorized?.()

    let data = null
    try {
      data = JSON.parse(await response.text())
    } catch {
      data = null // 连 JSON 都不是（网关的 HTML 错误页），交给 messageFrom 兜底
    }

    throw new ApiError(messageFrom(data, response.status), response.status, data)
  }

  return { blob: await response.blob(), filename: filenameFrom(response.headers) }
}

/**
 * 拼查询串。`undefined` / `null` / 空串的字段直接丢掉 ——
 * 后端的查询参数几乎都是 `X | None = None`，传空串反而会当成「筛选空值」。
 *
 * 没用 URLSearchParams：微信小程序里没有这个全局对象，
 * 这层是要原样搬去 uniapp 的，宁可自己拼十来行。
 */
export function buildQuery(params) {
  const parts = Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)

  return parts.length ? `?${parts.join('&')}` : ''
}
