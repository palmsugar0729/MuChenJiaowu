/**
 * 账号管理接口（管理员）。路径对照后端 codes/server/app/routers/admin.py。
 *
 * ⚠️ 老师账号也是从这张表里取的 —— 排课表单要选「这节课谁来上」，
 *    而任课老师可能是管理员本人（超管亲自带课是有的），所以**别按 role 过滤**，
 *    只过滤 `is_active`。
 */

import { request } from './client'

/** 全员名册（含管理员自己）。返回 `list[UserRead]`，没有密码哈希。 */
export function listUsers() {
  return request('/admin/users')
}
