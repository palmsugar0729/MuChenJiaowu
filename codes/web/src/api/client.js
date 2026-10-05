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
