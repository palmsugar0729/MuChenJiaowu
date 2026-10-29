<script setup>
/**
 * 待审批（管理员）。
 *
 * 老师提了改期申请之后，管理员在这里看到待办 → 通过 / 驳回。
 * 通过**会真的把课的时间改掉**（那节课在旧日期上就没了）；驳回则什么都不动，
 * 只在申请上记一笔理由。
 *
 * ⚠️ **只做 pending 一档**，不做「已处理」tab —— 设计文档原话是「刻意保持轻」。
 *    历史留痕在库里和每节课的详情页上（`lesson.approval`），够查。
 *
 * 权限：**只给管理员**。入口是课程页顶部的横幅（老师根本看不到那个横幅），
 * router 的守卫也会拦手输 URL。
 */

import { computed, onMounted, ref } from 'vue'

import { approveApproval, listApprovals, rejectApproval } from '@/api/approvals'
import AppHeader from '@/components/AppHeader.vue'
import TabBar from '@/components/TabBar.vue'
import { formatDate, formatDateTime, formatTime } from '@/utils/date'

const rows = ref([])
const loading = ref(true)
const error = ref('')
/** 操作反馈（通过了 / 驳回了），跟 error 分开显示 */
const notice = ref('')
/** 某一行的按钮正在跑 —— 只锁那一行，别整页禁用（别的行还能处理） */
const busyId = ref(null)

/**
 * 正在填驳回理由的那一行 id。
 *
 * ⚠️ 不用 `window.prompt`：部分内置浏览器的 WebView 会直接把它拦掉
 *    （小程序 WebView 尤其），点了没反应还不知道为什么。
 *    也**不引弹窗组件** —— AGENTS.md 明令：组件只抽真正重复且有真逻辑的东西。
 *    行内展开一个小卡片最省事，也最不容易出错。
 */
const rejectingId = ref(null)
const rejectReason = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    rows.value = await listApprovals('pending')
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(load)

/** 待办数，页头那句副标题用 */
const countText = computed(() => `共 ${rows.value.length} 条`)

async function approve(row) {
  // 改期是**真的改课**，而且改完旧日期上就没了 —— 值得一次确认。
  const ok = window.confirm(
    `确认把这节课改到 ${formatDate(row.new_date)} ${formatTime(row.new_start_time)} 吗？\n\n` +
      `${row.class_name} · ${row.teacher_name}`,
  )
  if (!ok) return

  error.value = ''
  notice.value = ''
  busyId.value = row.id
  try {
    await approveApproval(row.id)
    notice.value = `已通过：${row.class_name} 改到 ${formatDate(row.new_date)}`
    await load()
  } catch (e) {
    // ★ 「申请挂着的期间课被完成了」会走到这里（409）。**不要**在这里
    //   自动驳回或重试 —— 那节课到底该不该改，只有人知道。
    error.value = e.message
  } finally {
    busyId.value = null
  }
}

function startReject(row) {
  rejectingId.value = row.id
  rejectReason.value = ''
  error.value = ''
  notice.value = ''
}

async function confirmReject(row) {
  error.value = ''
  notice.value = ''
  busyId.value = row.id
  try {
    // 理由选填：空串时 api 那头会整个省掉 body
    await rejectApproval(row.id, rejectReason.value.trim())
    notice.value = `已驳回：${row.class_name}`
    rejectingId.value = null
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    busyId.value = null
  }
}
</script>

<template>
  <div class="page page--top page--tabbed">
    <div class="page__inner">
      <!-- 二级页（从课程页横幅点进来的），保留返回键 -->
      <AppHeader title="待审批" />

      <p v-if="error" class="alert">{{ error }}</p>
      <p v-if="notice" class="notice">{{ notice }}</p>

      <p v-if="loading" class="empty">加载中…</p>

      <p v-else-if="!rows.length" class="empty">没有待审批的改期申请</p>

      <template v-else>
        <p class="hint">{{ countText }} —— 通过会把课程真的改到新时间。</p>

        <div class="list">
          <div v-for="row in rows" :key="row.id" class="list__item">
            <p class="list__title">{{ row.class_name }} · {{ row.teacher_name }}</p>

            <!-- ★ 管理员要能对比「现在的」和「申请的」，所以两行都写全 -->
            <p class="list__meta">
              现在 {{ formatDate(row.lesson_date) }} {{ formatTime(row.lesson_start_time) }}
              <span class="arrow">→</span>
              <strong>申请改为 {{ formatDate(row.new_date) }} {{ formatTime(row.new_start_time) }}</strong>
            </p>

            <!-- 复用 base.css 的 `.lesson__content`：同一个视觉角色
                 （「一段要人读的正文」，浅底块 + 保留换行），只是内容换成了申请理由。
                 为一个配色一样的东西再抄一条 CSS 只会两边漂移。 -->
            <p class="lesson__content">理由：{{ row.reason }}</p>

            <p class="list__meta list__meta--quiet">
              {{ row.requested_by_name }} 提交于 {{ formatDateTime(row.requested_at) }}
            </p>

            <!-- 驳回理由面板（选填） -->
            <div v-if="rejectingId === row.id" class="reject">
              <textarea
                v-model="rejectReason"
                class="field__input"
                rows="2"
                placeholder="驳回理由（可以不填）"
              ></textarea>
              <div class="toolbar">
                <button
                  class="btn btn--sm"
                  type="button"
                  :disabled="busyId === row.id"
                  @click="confirmReject(row)"
                >
                  确认驳回
                </button>
                <button
                  class="btn btn--sm btn--ghost"
                  type="button"
                  @click="rejectingId = null"
                >
                  取消
                </button>
              </div>
            </div>

            <div v-else class="toolbar">
              <button
                class="btn btn--sm"
                type="button"
                :disabled="busyId === row.id"
                @click="approve(row)"
              >
                通过
              </button>
              <button
                class="btn btn--sm btn--ghost"
                type="button"
                :disabled="busyId === row.id"
                @click="startReject(row)"
              >
                驳回
              </button>
            </div>
          </div>
        </div>
      </template>
    </div>

    <TabBar />
  </div>
</template>

<style scoped>
/* 两行之间的箭头。用主色深一点的绿把「→」压下去，别跟日期抢注意力 */
.arrow {
  margin: 0 4px;
  color: var(--color-text-muted);
}

.reject {
  margin-top: 12px;
}

/* 驳回理由面板里的 toolbar 挨着 textarea，别留上面那截空白 */
.reject .toolbar {
  margin-top: 8px;
}
</style>
