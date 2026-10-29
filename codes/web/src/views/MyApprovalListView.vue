<script setup>
/**
 * 我的改期申请（老师）。
 *
 * 入口挂在「我的」页 —— 为什么不放课程详情页：那里只带**最近一条**申请
 * （`lesson.approval`，后端 `latest_for_lesson` 按 id desc 取一条）。
 * 老师提过两次之后，前一条（比如撤回的那条）就看不见了 —— 用户 2026-10-29 报的。
 * 数据一直在库里，这一页把它列全。
 *
 * ⚠️ **只读**：撤回仍然在那节课的详情页做（`withdrawApproval`）。
 *    这里不重复放操作按钮，免得同一个动作有两个入口、两处状态要同步。
 *
 * **一页 10 条**（用户 2026-10-29 定的）：申请会一年年攒下去，一次全铺开在手机上
 * 要滑很久，而且越滑越不知道自己在第几条。分页在**前端切**（后端 `/approvals/my`
 * 照样一次返回全部）—— 一个老师一辈子的申请也就几十条，为它加一套分页契约不值得。
 *
 * ⚠️ 页码放 `route.query.page` 不放 `ref`：刷新还在第 2 页、链接能直接发人
 * （同课程日视图的 `date`、计薪的 `month`）。
 *
 * 名字叫 `me-approval-list` 不是随意的：`TabBar.isActive` 剥掉 `-list` 后按
 * **前缀**点亮 tab，`me` 才亮「我的」（`mine-...` 会五个 tab 全灭）。
 */

import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { listMyApprovals } from '@/api/approvals'
import AppHeader from '@/components/AppHeader.vue'
import TabBar from '@/components/TabBar.vue'
import { formatDate, formatDateTime, formatTime } from '@/utils/date'

const PAGE_SIZE = 10

const STATUS_LABELS = {
  pending: '待审批',
  approved: '已通过',
  rejected: '已驳回',
  withdrawn: '已撤回',
}

const STATUS_CLASSES = {
  pending: '',
  approved: 'tag--solid',
  rejected: 'tag--muted',
  withdrawn: 'tag--quiet',
}

const route = useRoute()
const router = useRouter()

const rows = ref([])
const loading = ref(true)
const error = ref('')

// URL 里的页码。手改出来的乱七八糟的值（`?page=abc` / `?page=-1`）一律当第 1 页
const page = computed(() => {
  const raw = Number(route.query.page)
  return Number.isInteger(raw) && raw > 0 ? raw : 1
})

const totalPages = computed(() => Math.max(1, Math.ceil(rows.value.length / PAGE_SIZE)))

// ★ 真正渲染用的页码要**再夹一次**：列表可能变短（数据少了、手改 URL、或之前那页
//   本来就不存在），越界就按最后一页显示 —— 不然会看到一张空白页，还以为没数据
const currentPage = computed(() => Math.min(page.value, totalPages.value))

const pageRows = computed(() => {
  const start = (currentPage.value - 1) * PAGE_SIZE
  return rows.value.slice(start, start + PAGE_SIZE)
})

// 越界的同时把 URL 修回来，免得地址栏一直指着一个不存在的页码。
// ⚠️ 两个都要看：只盯 `totalPages` 会漏掉「数据直接就没超过 10 条」（它压根没变化），
//    那种情况下 `?page=5` 会一直挂在地址栏上
watch([page, totalPages], ([wanted, total]) => {
  if (wanted > total) {
    router.replace({ query: { ...route.query, page: total } })
  }
})

function goPage(offset) {
  const target = currentPage.value + offset
  if (target < 1 || target > totalPages.value) return
  // replace 不是 push：翻页不该在浏览器历史里留一串脚印，返回键要直接回「我的」
  router.replace({ query: { ...route.query, page: target } })
  // 分页条在列表下方，翻完页人还待在屏幕底部 —— 不回顶会以为「翻页没生效」
  window.scrollTo(0, 0)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    rows.value = await listMyApprovals()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page page--top page--tabbed">
    <div class="page__inner">
      <!-- 二级页（从「我的」点进来的），保留返回键 -->
      <AppHeader title="我的改期申请" />

      <p v-if="error" class="alert">{{ error }}</p>

      <p v-if="loading" class="empty">加载中…</p>

      <p v-else-if="!rows.length" class="empty">还没有提交过改期申请</p>

      <div v-else>
        <div class="list">
          <div v-for="row in pageRows" :key="row.id" class="list__item">
            <div class="row">
              <strong>{{ row.class_name || '课程已删除' }}</strong>
              <span class="tag" :class="STATUS_CLASSES[row.status]">
                {{ STATUS_LABELS[row.status] }}
              </span>
            </div>

            <!-- 现在 → 申请改为。管理员审批时看的是这两行，老师回看也一样 -->
            <p class="list__meta">
              现在 {{ formatDate(row.lesson_date) }} {{ formatTime(row.lesson_start_time) }}
              <span class="arrow">→</span>
              申请改为 {{ formatDate(row.new_date) }} {{ formatTime(row.new_start_time) }}
            </p>

            <!-- 复用 base.css 的 `.lesson__content`：同一个视觉角色
                 （「一段要人读的正文」，浅底块 + 保留换行） -->
            <p class="lesson__content">理由：{{ row.reason }}</p>

            <p v-if="row.reject_reason" class="list__meta">
              驳回理由：{{ row.reject_reason }}
            </p>

            <p class="list__meta list__meta--quiet">
              提交于 {{ formatDateTime(row.requested_at) }}
              <template v-if="row.reviewed_at">
                · {{ row.reviewed_by_name || '管理员' }} 处理于
                {{ formatDateTime(row.reviewed_at) }}
              </template>
            </p>
          </div>
        </div>

        <!-- 只有一页就不显示分页条：一个孤零零的「第 1 / 1 页」只会让人以为还有 -->
        <div v-if="totalPages > 1" class="pager">
          <button
            class="btn btn--ghost btn--sm"
            type="button"
            :disabled="currentPage === 1"
            @click="goPage(-1)"
          >
            上一页
          </button>
          <span class="pager__info">
            第 {{ currentPage }} / {{ totalPages }} 页 · 共 {{ rows.length }} 条
          </span>
          <button
            class="btn btn--ghost btn--sm"
            type="button"
            :disabled="currentPage === totalPages"
            @click="goPage(1)"
          >
            下一页
          </button>
        </div>
      </div>
    </div>

    <TabBar />
  </div>
</template>

<style scoped>
/* 两行之间的箭头。同 ApprovalListView —— 用淡一点的颜色把「→」压下去 */
.arrow {
  margin: 0 4px;
  color: var(--color-text-muted);
}

/* 翻页条：跟 MineView 的「上月 / 月份 / 下月」同一种排法 ——
   两边是按钮（`.btn--sm` 让它们不占满整行），中间的字 `flex: 1` 吃掉剩余空间。
   ⚠️ `min-width: 0` 不能省，否则长文案会把这一行撑破 */
.pager {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 16px;
}

.pager__info {
  flex: 1;
  min-width: 0;
  text-align: center;
  font-size: 13px;
  color: var(--color-text-muted);
}
</style>
