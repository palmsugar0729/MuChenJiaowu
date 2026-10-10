<script setup>
/**
 * 课程日视图。老师每天真正要用的那个页面。
 *
 * 选中的日期放在 **URL 的 query 里**（`/lessons?date=2026-10-05`），不放组件状态：
 * 这样「进详情 → 返回」不会把日期丢掉，刷新页面也还在同一天，链接还能直接发给人。
 */

import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { listLessons } from '@/api/lessons'
import AppHeader from '@/components/AppHeader.vue'
import TabBar from '@/components/TabBar.vue'
import { useAuthStore } from '@/stores/auth'
import { formatTime, shiftDays, todayISO, weekdayLabel } from '@/utils/date'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const STATUS_LABELS = {
  scheduled: '已排课',
  completed: '已完成',
  cancelled: '已取消',
}

const STATUS_CLASSES = {
  scheduled: '',
  completed: 'tag--solid',
  cancelled: 'tag--muted',
}

/** 默认今天。⚠️ 用 todayISO()，不是 toISOString().slice(0,10) —— 那是 UTC 日期。 */
const date = computed(() => route.query.date || todayISO())

const list = ref([])
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    list.value = await listLessons({ date: date.value })
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(load)

// 日期变化就重拉。用 watch 而不是在每个入口手动调 load()：
// 浏览器前进/后退也会改 query，那也得跟着走。
watch(date, load)

function goTo(next) {
  if (!next) return // <input type="date"> 被清空时给的就是空串
  router.replace({ name: 'lesson-list', query: { date: next } })
}

/**
 * 切到月视图。带上当天，让月历直接落在这一天的那个月，并选中它 ——
 * 否则从 3 月某天切过去会掉回「今天所在的月」，人就找不着自己刚才在看哪儿了。
 *
 * ★ 月视图的月份是**从 date 派生**的，不另传 month 参数 ——
 *   两个参数会变成两个真相源（网格和下面的列表能各说各话）。
 */
function goMonthView() {
  router.replace({ name: 'lesson-month', query: { date: date.value } })
}

function dayLabel() {
  return date.value === todayISO() ? '今天' : weekdayLabel(date.value)
}

/** 从详情页返回时把当天的日期带上，别让人回到「今天」再重新找一遍。 */
function openLesson(item) {
  router.push({ name: 'lesson-detail', params: { id: item.id }, query: { date: date.value } })
}

function addLesson() {
  router.push({ name: 'lesson-new', query: { date: date.value } })
}
</script>

<template>
  <div class="page page--top page--tabbed">
    <div class="page__inner">
      <!-- 一级页面，没有「上一页」可退 -->
      <AppHeader title="课程" :back="false">
        <template #actions>
          <button
            v-if="auth.isAdmin"
            class="btn btn--sm btn--ghost"
            type="button"
            @click="addLesson"
          >
            排课
          </button>
        </template>
      </AppHeader>

      <p v-if="error" class="alert">{{ error }}</p>

      <!-- 日 / 月 视图切换。两处各写一遍不抽组件 —— 见 AGENTS.md
           「三态分段控件、分类卡都用 CSS 类不抽组件」。 -->
      <div class="segmented">
        <button class="segmented__btn segmented__btn--on" type="button">日</button>
        <button class="segmented__btn" type="button" @click="goMonthView">月</button>
      </div>

      <div class="card">
        <div class="field">
          <label class="field__label" for="lesson-date">
            {{ dayLabel() }} · {{ date }}
          </label>
          <input
            id="lesson-date"
            class="field__input"
            type="date"
            :value="date"
            @change="goTo($event.target.value)"
          />
        </div>

        <div class="toolbar">
          <button
            class="btn btn--ghost"
            type="button"
            @click="goTo(shiftDays(date, -1))"
          >
            前一天
          </button>
          <button class="btn btn--ghost" type="button" @click="goTo(todayISO())">
            今天
          </button>
          <button
            class="btn btn--ghost"
            type="button"
            @click="goTo(shiftDays(date, 1))"
          >
            后一天
          </button>
        </div>
      </div>

      <p v-if="loading" class="hint">加载中…</p>

      <template v-else>
        <p v-if="!list.length" class="empty">这一天没有课</p>

        <div v-else class="list">
          <button
            v-for="item in list"
            :key="item.id"
            class="list__item"
            type="button"
            @click="openLesson(item)"
          >
            <div class="row">
              <strong>{{ formatTime(item.start_time) }} · {{ item.class_name }}</strong>
              <span class="tag" :class="STATUS_CLASSES[item.status]">
                {{ STATUS_LABELS[item.status] }}
              </span>
            </div>
            <p class="list__meta">
              {{ item.teacher_name }} · {{ item.hours }} 课时 · ¥{{ item.rate }}/时
            </p>

            <!-- ★ 上课内容（「这节课上到哪了」）。只有上过的课才有，
                 排课时的 note 不在这儿显示 —— 那是给排课的人看的内部备注 -->
            <p v-if="item.content" class="lesson__content">{{ item.content }}</p>
          </button>
        </div>

        <p v-if="!auth.isAdmin" class="hint">这里只有你自己的课</p>
      </template>
    </div>

    <TabBar />
  </div>
</template>

<style scoped>
/* 「日 / 月」分段控件与日期卡之间要留缝。`.segmented` 只有 margin-top、
   `.card` 没有 margin —— 不补的话控件会跟白卡片贴死。
   （班级页没这个问题，是因为它下面垫了个 44px 高的 .checkbox。同 MineView 的写法） */
.card {
  margin-top: 16px;
}
</style>
