/**
 * 本地存储适配器 —— 全项目唯一允许碰 localStorage 的地方。
 *
 * 将来移植 uniapp 时只改这一个文件（换成 uni.getStorageSync 系列），
 * 其它代码一行都不用动。所以：**别在别处直接写 localStorage**。
 */
export const storage = {
  get(key) {
    try {
      return localStorage.getItem(key)
    } catch {
      return null
    }
  },

  set(key, value) {
    try {
      localStorage.setItem(key, value)
    } catch {
      // 隐私模式、存储配额满 —— 不值得让整个应用挂掉，静默降级为不持久化
    }
  },

  remove(key) {
    try {
      localStorage.removeItem(key)
    } catch {
      // 同上
    }
  },
}
