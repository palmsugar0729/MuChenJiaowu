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

    /** 班级类型 → 在册人数上限，例：{ '1对1': 1, '1对2': 2, '1对3': 5, ... } */
    capacities: (s) => s.rules?.capacities || {},

    smallPrefix: (s) => s.rules?.small_prefix || 'XB',

    /**
     * 新建学生自动送的课时数。
     *
     * ⚠️ **不要在这个文件里写死 48**，也不要在页面里抄一份 —— 真相源在后端
     * `core/config.py` 的 `default_student_hours`，这里只是把它带出去给表单提示。
     * 拿不到时给 0，提示那行就自动不显示了（宁可不提示，也别提示错数字）。
     */
    defaultStudentHours: (s) => s.rules?.default_student_hours ?? 0,

    /**
     * 班级列表顶部的分类卡，例：
     *   [{ key: 'ydy', label: '1对1', types: ['1对1'] },
     *    { key: 'yde', label: '1对2', types: ['1对2'] },
     *    { key: 'xb',  label: '小班',  types: ['1对3','1对4','1对5'] }]
     *
     * ★ `label` 是给用户看的**人话**，`key` 只进 URL。
     *   用户 2026-10-07 提的：卡面上不能出现 YDY / XB 这种内部编码，老师看不懂。
     *
     * ⚠️ 筛选按 `types` 里的 **class_type** 比，**不是**按班级名前缀 ——
     *    历史遗留的自定义班名（「沐晨提高班」这种）没有前缀，
     *    按前缀筛会让它们只在「总览」里有，切到「1对1」就消失了。
     *
     * 「总览」那张卡不在这儿，是页面自己加的第一张。
     */
    classTabs: (s) => s.rules?.class_tabs || [],

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

    /**
     * 某类型最多能有几个**在册**学生；认不出的类型给 null = 不限制。
     *
     * ⚠️ 这不是「1对N → N」：小班三档（1对3/1对4/1对5）**共用 5 人上限**。
     *    所以别在这儿自己算，一律用后端给的 `capacities`。
     */
    capacityFor(classType) {
      return this.capacities[classType] ?? null
    },
  },
})
