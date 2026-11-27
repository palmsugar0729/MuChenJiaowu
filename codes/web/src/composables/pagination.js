/**
 * 列表分页（用户 2026-11-27 定：**班级、学生一页最多 5 个**，「不然看着太多了」）。
 *
 * ★ 页码放 **`route.query.page`**，跟其他视图状态一个待遇：
 *   刷新还在第 2 页、进详情再返回不掉、链接能直接发人。
 * ⚠️ 分页在**前端切**：班级 / 学生列表本来就是一次拉全部的（后端没有
 *   offset/limit 契约），几十条数据犯不上为它加一套分页接口。
 * ⚠️ 手改出来的乱七八糟页码（`?page=abc` / `?page=99`）一律夹回合法范围 ——
 *   不夹的话会显示一张空白页，看着像「没数据了」。
 */
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

/** 一页几条。用户 2026-11-27 定的数 */
export const PAGE_SIZE = 5

/**
 * @param {import('vue').Ref<Array>} items 已经筛好的完整列表
 * @param {number} perPage 一页几条，默认 5
 */
export function usePagination(items, perPage = PAGE_SIZE) {
  const route = useRoute()
  const router = useRouter()

  const totalPages = computed(() =>
    Math.max(1, Math.ceil(items.value.length / perPage)),
  )

  /** 当前页（已夹到 1~totalPages）。URL 里没有就第 1 页 */
  const page = computed(() => {
    const raw = Number(route.query.page)
    if (!Number.isInteger(raw) || raw < 1) return 1
    return Math.min(raw, totalPages.value)
  })

  const pageItems = computed(() => {
    const start = (page.value - 1) * perPage
    return items.value.slice(start, start + perPage)
  })

  /** 改 URL 里的页码。第 1 页就把参数去掉，保持地址栏干净 */
  function setPage(n) {
    const query = { ...route.query }
    if (n <= 1) delete query.page
    else query.page = String(n)
    router.replace({ query })
  }

  function goPage(offset) {
    const target = page.value + offset
    if (target < 1 || target > totalPages.value) return
    setPage(target)
  }

  /**
   * 换筛选条件 / 重新搜索时调一次 —— 不然搜完还停在第 3 页，
   * 结果只有 2 条就是一张空白页。
   */
  function resetPage() {
    if (route.query.page === undefined) return
    const query = { ...route.query }
    delete query.page
    router.replace({ query })
  }

  // 数据变少 / 手改 URL 时把越界的页码修回来。
  // ⚠️ 盯的是**原始值**（不是夹过之后的 page），否则 `?page=99` 会被显示成最后一页，
  //    但地址栏一直挂着 99，刷新回来又变一次。
  watch([() => route.query.page, totalPages], () => {
    const raw = Number(route.query.page)
    if (!Number.isInteger(raw) || raw < 1) return
    if (raw > totalPages.value) setPage(totalPages.value)
  })

  return { page, totalPages, pageItems, goPage, resetPage }
}
