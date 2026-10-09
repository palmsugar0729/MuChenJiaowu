<script setup>
/**
 * 「我的」—— 账号信息 + 计薪统计 + 工资表下载 + 退出登录。
 *
 * 计薪和导出**挂在这一页**（用户 2026-10-08 定的）：不新增底部 tab、不新增一级页面。
 * 老师真正会点它的时刻是月底「把这个月工资表发给领导」，那本来就是收尾动作，
 * 跟「我是谁 / 退出登录」待在一起最顺。
 *
 * ⚠️ 月份存在 `route.query.month` 而不是 `ref`，理由同课程日视图的 `route.query.date`：
 *    刷新还在当月、返回不丢、链接能直接发给别人。所以用 `watch(month, load)` 而不是
 *    在每个入口手动调 —— 点月份选择器、点上下月、浏览器前进后退都会走到那儿。
 */

import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { exportPayroll, myPayroll, payrollSummary } from '@/api/payroll'
import AppHeader from '@/components/AppHeader.vue'
import TabBar from '@/components/TabBar.vue'
import { useAuthStore } from '@/stores/auth'
import { formatDate, formatTime, monthOf, shiftMonths, todayISO } from '@/utils/date'
import { saveBlob } from '@/utils/download'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const ROLE_LABELS = {
  super_admin: '超级管理员',
  admin: '管理员',
  teacher: '老师',
}

const roleLabel = computed(() => ROLE_LABELS[auth.user?.role] || auth.user?.role || '')

// ⚠️ 用 monthOf(todayISO()) 按**本地时间**取当月，不是 toISOString().slice(0, 7)
const month = computed(() => route.query.month || monthOf(todayISO()))

const mine = ref(null)
const overview = ref(null)
const loading = ref(false)
const downloading = ref(false)
const error = ref('')
const notice = ref('')

async function load(value) {
  loading.value = true
  error.value = ''
  notice.value = ''
  try {
    // ⚠️ 管理员要两次请求。用 Promise.all 而不是 await 两次 —— 手机上串行等待
    //    就是两倍的转圈时间，而这两个请求彼此无关。
    const [my, summary] = await Promise.all([
      myPayroll(value),
      auth.isAdmin ? payrollSummary(value) : Promise.resolve(null),
    ])
    mine.value = my
    overview.value = summary
  } catch (e) {
    error.value = e.message
    // ⚠️ 失败要清干净。留着上一轮的数据，用户会以为「切换月份没生效」
    mine.value = null
    overview.value = null
  } finally {
    loading.value = false
  }
}

watch(month, load, { immediate: true })

function goMonth(offset) {
  router.replace({ query: { ...route.query, month: shiftMonths(month.value, offset) } })
}

function onMonthChange(event) {
  const value = event.target.value
  if (value && value !== month.value) {
    router.replace({ query: { ...route.query, month: value } })
  }
}

// 页面上只做展示，格式化的脏活集中在这儿 —— 后端的数字原样是 6 / 6.0 / 120.0
const fmtHours = (value) => String(Number(value ?? 0))
const fmtMoney = (value) => Number(value ?? 0).toFixed(2)

const hasLessons = computed(() => (mine.value?.lessons?.length ?? 0) > 0)
const hasOverview = computed(() => (overview.value?.teachers?.length ?? 0) > 0)

async function download(teacherId) {
  downloading.value = true
  error.value = ''
  notice.value = ''
  try {
    const { blob, filename } = await exportPayroll({ month: month.value, teacherId })
    // filename 是后端 Content-Disposition 里的中文名；解不出来就自己拼一个
    saveBlob(blob, filename || `工资结算表_${month.value}.xlsx`)
    notice.value = '工资表已开始下载，请到「下载」里查看'
  } catch (e) {
    error.value = e.message
  } finally {
    downloading.value = false
  }
}

function logout() {
  auth.logout()
  router.replace({ name: 'login' })
}
</script>

<template>
  <div class="page page--top page--tabbed">
    <div class="page__inner">
      <!-- 一级页面，没有「上一页」可退 -->
      <AppHeader title="我的" :back="false" />

      <div class="card">
        <p class="mine__name">{{ auth.displayName }}</p>
        <p class="mine__meta">{{ auth.user?.phone }} · {{ roleLabel }}</p>
      </div>

      <div class="month">
        <button class="btn btn--ghost btn--sm" type="button" @click="goMonth(-1)">上月</button>
        <input
          class="field__input month__input"
          type="month"
          :value="month"
          @change="onMonthChange"
        />
        <button class="btn btn--ghost btn--sm" type="button" @click="goMonth(1)">下月</button>
      </div>

      <p v-if="error" class="alert">{{ error }}</p>
      <p v-if="notice" class="notice">{{ notice }}</p>

      <div class="card">
        <p class="section">本月计薪</p>

        <p v-if="loading" class="empty">加载中…</p>

        <template v-else-if="mine">
          <div class="stats">
            <div class="stat">
              <div class="stat__value">{{ fmtHours(mine.total_hours) }}</div>
              <div class="stat__label">课时数</div>
            </div>
            <div class="stat">
              <div class="stat__value">{{ fmtMoney(mine.total_salary) }}</div>
              <div class="stat__label">课时费（元）</div>
            </div>
          </div>

          <!-- ★ 逐节明细：下载前先自己对一遍，金额不对时有据可查 -->
          <template v-if="hasLessons">
            <p class="section">逐节明细</p>
            <div class="list">
              <div
                v-for="item in mine.lessons"
                :key="item.lesson_id"
                class="list__item"
              >
                <p class="list__title">
                  {{ formatDate(item.lesson_date) }} {{ formatTime(item.start_time) }}
                </p>
                <p class="list__meta">
                  {{ item.class_name }} · {{ item.class_type }} ·
                  {{ fmtHours(item.hours) }} 课时 × {{ fmtMoney(item.rate) }} 元
                </p>
                <p class="list__meta list__meta--quiet">
                  薪酬 {{ fmtMoney(item.salary) }} 元
                  <template v-if="item.note"> · {{ item.note }}</template>
                </p>
              </div>
            </div>
          </template>

          <p v-else class="empty">{{ month }} 没有已完成的课程</p>

          <div class="toolbar">
            <button
              class="btn"
              type="button"
              :disabled="!hasLessons || downloading"
              @click="download()"
            >
              {{ downloading ? '正在导出…' : '下载我的工资表' }}
            </button>
          </div>
        </template>
      </div>

      <!-- 管理员才有：全体汇总 + 一个多 sheet 的文件 -->
      <div v-if="auth.isAdmin" class="card">
        <p class="section">全部老师</p>

        <div v-if="hasOverview" class="list">
          <div
            v-for="teacher in overview.teachers"
            :key="teacher.teacher_id"
            class="list__item"
          >
            <p class="list__title">{{ teacher.teacher_name }}</p>
            <p class="list__meta">
              {{ teacher.lesson_count }} 节 · {{ fmtHours(teacher.total_hours) }} 课时 ·
              {{ fmtMoney(teacher.total_salary) }} 元
            </p>
          </div>
        </div>

        <p v-else class="empty">{{ month }} 没有已完成的课程</p>

        <div class="toolbar">
          <button
            class="btn"
            type="button"
            :disabled="!hasOverview || downloading"
            @click="download()"
          >
            {{ downloading ? '正在导出…' : '导出所有人的工资表' }}
          </button>
        </div>
      </div>

      <div class="toolbar">
        <button
          class="btn btn--ghost"
          type="button"
          @click="router.push({ name: 'change-password' })"
        >
          修改密码
        </button>
        <button class="btn btn--ghost" type="button" @click="logout">退出登录</button>
      </div>

      <p class="hint">审批、月视图课表还在开发中</p>
    </div>

    <TabBar />
  </div>
</template>

<style scoped>
.mine__name {
  margin: 0 0 4px;
  font-size: 18px;
  font-weight: 600;
}

.mine__meta {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-muted);
}

/* 月份选择：两边是「上月 / 下月」，中间是原生的 type="month" */
.month {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 16px;
}

.month__input {
  /* flex:1 且 min-width:0，否则 input 的默认固有宽度会把这一行撑破 */
  flex: 1;
  min-width: 0;
  text-align: center;
}

.card {
  margin-top: 16px;
}
</style>
