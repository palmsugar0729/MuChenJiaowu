/**
 * 认证相关接口。纯函数，零平台依赖 —— 移植 uniapp 时原样搬走。
 *
 * 路径对照后端 codes/server/app/routers/auth.py，前缀 /api 由 client 补。
 */

import { request } from './client'

/** 登录。auth: false —— 这时候还没有 token，带上也没意义。 */
export function login(phone, password) {
  return request('/auth/login', {
    method: 'POST',
    body: { phone, password },
    auth: false,
  })
}

/**
 * 改自己的密码。
 * 注意：后端只回 {message: "密码已修改"}，**不回 user** ——
 * 调用方得自己把本地的 must_change_password 置回 false。
 */
export function changePassword(oldPassword, newPassword) {
  return request('/auth/change-password', {
    method: 'POST',
    body: { old_password: oldPassword, new_password: newPassword },
  })
}

/** 当前登录用户。刷新页面后用它还原身份。 */
export function getMe() {
  return request('/users/me')
}

/** 改自己的姓名 / 手机号（is_active 传了会被后端拒掉）。 */
export function updateMe(patch) {
  return request('/users/me', { method: 'PATCH', body: patch })
}
