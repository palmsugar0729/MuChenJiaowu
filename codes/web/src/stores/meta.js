/**
 * 参考数据 —— 班级名前缀规则 + 费率表。
 *
 * 这东西的唯一真相源在**后端**（`GET /classes/rules`，源头是
 * codes/server/app/core/class_rules.py）。前端这份**只是即时反馈**：
 * 让「输入 YDY001 就自动锁定 1对1」当场看得见，省得填完才吃 400。
 * 两边万一不一致，写进库里的仍以后端判定为准，不会脏数据。
 *
 * 所以：**别把规则硬编码在这个文件里**，也别在页面里再抄一份。
 */

import { defineStore } from 'pinia'

import { getClassRules } from '@/api/classes'

export const useMetaStore = defineStore('meta', {
  state: () => ({
    rules: null,
    // 存的是 Promise 而不是布尔：两个页面同时挂载时只会发一次请求
    pending: null,
  }),

  getters: {
    /** 班级类型 → 费率。例：{ '1对1': 80, '1对2': 100, ... } */
    rates: (s) => s.rules?.rates || {},

    /** 所有可选班级类型（就是费率表的键）。 */
    allTypes: (s) => Object.keys(s.rules?.rates || {}),

    smallPrefix: (s) => s.rules?.small_prefix || 'XB',

    loaded: (s) => !!s.rules,
  },

  actions: {
    /** 取一次就缓存住。force 用来在出错后重试。 */
    async load(force = false) {
      if (this.rules && !force) return this.rules
      if (this.pending) return this.pending

      this.pending = getClassRules()
        .then((rules) => {
          this.rules = rules
          return rules
        })
        .finally(() => {
          this.pending = null
        })

      return this.pending
    },

    /**
     * 按班级名推断类型规则。**逻辑与后端 `class_type_rule()` 逐条对齐**
     * （codes/server/app/core/class_rules.py）：
     *
     *   YDY / YDE → fixed，类型锁死，界面不该让改
     *   XB        → small，从 1对3/1对4/1对5 里自己挑，**不预选**
     *   其他      → free，全部类型随便选
     *
     * @returns {{mode: 'fixed'|'small'|'free', options: string[], default: string|null}}
     */
    classTypeRule(name) {
      // 后端也是 strip().upper() 之后再比对，大小写和首尾空格都不影响判定
      const key = (name || '').trim().toUpperCase()
      const all = this.allTypes

      for (const [prefix, type] of this.rules?.class_name_rules || []) {
        if (key.startsWith(prefix)) {
          return { mode: 'fixed', options: [type], default: type }
        }
      }

      if (key && key.startsWith(this.smallPrefix)) {
        // 这里**故意不用 small_default 预选**：后端对 XB 要求显式指定类型，
        // 前端替他选了，用户就永远看不出「这个必须自己挑」。
        return { mode: 'small', options: this.rules?.small_types || [], default: null }
      }

      return { mode: 'free', options: all, default: null }
    },

    /** 某类型的建议费率；表里没有就给 null（让用户自己填，别猜）。 */
    rateFor(classType) {
      return this.rates[classType] ?? null
    },
  },
})
