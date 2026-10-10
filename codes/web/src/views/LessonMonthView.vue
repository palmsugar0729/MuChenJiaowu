<script setup>
/**
 * 课程月视图。老师想知道「这个月哪天有课」，不用一天一天点「后一天」翻三十下。
 *
 * ★ **`date` 是唯一真相源，`month` 由它派生** —— 不另开一个 `month` query 参数。
 *   两个参数会变成两个真相源，必然出现「网格画 10 月、下面列表列 3 月」这种
 *   自相矛盾的屏（日视图停在 3-15 切过来、翻月只改 month 不改 date、
 *   手改 URL 只给一个参数 —— 三条路都通向它）。
 *
 * 数据**一次拉整月**（`listLessons({ month })`），当天列表在本地筛：
 * 点一天不该再跑一趟接口。
 *
 * 后端零改动 —— `GET /lessons?month=YYYY-MM` 从 Phase 2 起就是给月视图预留的。
 */

import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { listLessons } from '@/api/lessons'
import AppHeader from '@/components/AppHeader.vue'
import TabBar from '@/components/TabBar.vue'
import { useAuthStore } from '@/stores/auth'
import {
  MONTH_WEEKDAYS,
  formatTime,
  monthGrid,
  monthOf,
  moveDayToMonth,
  shiftMonths,
  todayISO,
  weekdayLabel,
} from '@/utils/date'

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

/** 选中日期。缺省今天。⚠️ 用 todayISO()，不是 toISOString().slice(0,10) —— 那是 UTC 日期。 */
const date = computed(() => route.query.date || todayISO())

/** ★ 网格画哪个月。从 `date` 派生，**不是**第二个 query 参数。 */
const month = computed(() => monthOf(date.value))

const cells = computed(() => monthGrid(month.value))

const lessons = ref([])
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    lessons.value = await listLessons({ month: month.value })
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(load)

// 只在**换月**时重拉。点某一天只改 date、不改 month，不该再跑一趟接口。
// 用 watch 而不是在每个入口手动调 load()：浏览器前进/后退也会改 query，那也得跟着走。
watch(month, load)

/**
 * 每天有几节课，用来画底色和右下角的徽标。
 *
 * ⚠️ **已取消的课不算** —— 取消了的那天其实没课，标上底色会让人白跑一趟。
 *    下面展开的列表是**另一个口径**（含已取消），见 `dayLessons`。
 */
const countByDay = computed(() => {
  const counts = {}
  for (const lesson of lessons.value) {
    if (lesson.status === 'cancelled') continue
    counts[lesson.lesson_date] = (counts[lesson.lesson_date] || 0) + 1
  }
  return counts
})

function countOf(iso) {
  return countByDay.value[iso] || 0
}

/** 一天超过 9 节课就写「9+」，格子就那么大。 */
function badge(count) {
  return count > 9 ? '9+' : String(count)
}

/**
 * ★ **故意和徽标是两个口径**：这里**含**已取消的课（带灰色「已取消」标签），
 *   跟日视图 `listLessons({ date })` 的行为一致 —— 那天本来安排了什么得看得见。
 *   顺序由后端保证（`order_by(lesson_date, start_time, id)`），前端不再排。
 */
const dayLessons = computed(() =>
  lessons.value.filter((lesson) => lesson.lesson_date === date.value),
)

const monthLabel = computed(() => {
  const [year, mon] = month.value.split('-')
  return `${year} 年 ${Number(mon)} 月`
})

const dayLabel = computed(() => {
  const head = date.value === todayISO() ? '今天' : weekdayLabel(date.value)
  return `${head} · ${date.value}`
})

/** 格子的无障碍名。日历格子只有个数字，读屏得靠它。 */
function cellLabel(cell) {
  const count = countOf(cell.iso)
  return `${cell.iso} ${weekdayLabel(cell.iso)}，${count ? `${count} 节课` : '没有课'}`
}

/**
 * 换日期。
 * ★ 和选天、翻月一样统一用 `replace`（日视图 `goTo`、班级页 `selectTab` 也是）：
 *   视图和日期都只是「课程」这个 tab 上的过滤器，不是导航层级，
 *   别让后退键在每一天之间走一遍。代价是后退不回到日视图，直接离开课程区。
 */
function goDate(next) {
  if (!next) return // 手输 URL 被改坏、<input> 被清空都可能给空串
  router.replace({ name: 'lesson-month', query: { date: next } })
}

/**
 * 翻月 / 改月份输入框。
 * **把「几号」带过去**（10-31 翻到 11 月 → 11-30），否则日期会溢出到下个月，
 * 网格和下面的列表又要各说各话。
 */
function goMonth(target) {
  if (!target) return // <input type="month"> 被清空时给的就是空串
  goDate(moveDayToMonth(date.value, target))
}

/** 切回日视图，把选中那天带过去。 */
function goDayView() {
  router.replace({ name: 'lesson-list', query: { date: date.value } })
}

/** 把选中那天也带上，方便详情页的「返回当天课表」回到同一天。 */
function openLesson(item) {
  router.push({
    name: 'lesson-detail',
    params: { id: item.id },
    query: { date: date.value },
  })
}
</script>

<template>
  <div class="page page--top page--tabbed">
    <div class="page__inner">
      <!-- 一级页面，没有「上一页」可退 -->
      <AppHeader title="课程" :back="false" />

      <p v-if="error" class="alert">{{ error }}</p>

      <!-- 日 / 月 视图切换（和日视图同一排）。两处各写一遍不抽组件 ——
           见 AGENTS.md「三态分段控件、分类卡都用 CSS 类不抽组件」。 -->
      <div class="segmented">
        <button class="segmented__btn" type="button" @click="goDayView">日</button>
        <button class="segmented__btn segmented__btn--on" type="button">月</button>
      </div>

      <div class="card">
        <div class="field">
          <label class="field__label" for="lesson-month">{{ monthLabel }}</label>
          <input
            id="lesson-month"
            class="field__input"
            type="month"
            :value="month"
            @change="goMonth($event.target.value)"
          />
        </div>

        <div class="toolbar">
          <button
            class="btn btn--ghost"
            type="button"
            @click="goMonth(shiftMonths(month, -1))"
          >
            上月
          </button>
          <button class="btn btn--ghost" type="button" @click="goDate(todayISO())">
            今天
          </button>
          <button
            class="btn btn--ghost"
            type="button"
            @click="goMonth(shiftMonths(month, 1))"
          >
            下月
          </button>
        </div>
      </div>

      <p v-if="loading" class="hint">加载中…</p>

      <template v-else>
        <!-- ★ 月历**满宽，不套 .card**：套进去左右各 20px，360px 的安卓机上
             格子只剩 ~39px，跌破 44px 的触控目标。所以它是 .page__inner 的
             直接子元素，白底和圆角自己带。 -->
        <div class="calendar">
          <span v-for="w in MONTH_WEEKDAYS" :key="w" class="calendar__weekday">
            {{ w }}
          </span>

          <template v-for="(cell, index) in cells" :key="cell ? cell.iso : `blank-${index}`">
            <span v-if="!cell" class="calendar__blank" aria-hidden="true"></span>

            <button
              v-else
              class="calendar__day"
              :class="{
                'calendar__day--has': countOf(cell.iso) > 0,
                'calendar__day--today': cell.iso === todayISO(),
                'calendar__day--on': cell.iso === date,
              }"
              type="button"
              :aria-label="cellLabel(cell)"
              :aria-current="cell.iso === date ? 'date' : undefined"
              @click="goDate(cell.iso)"
            >
              <span class="calendar__num">{{ cell.day }}</span>
              <span v-if="countOf(cell.iso)" class="calendar__count">
                {{ badge(countOf(cell.iso)) }}
              </span>
            </button>
          </template>
        </div>

        <p class="section">{{ dayLabel }}</p>

        <p v-if="!dayLessons.length" class="empty">这一天没有课</p>

        <div v-else class="list">
          <button
            v-for="item in dayLessons"
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
/* 「日 / 月」分段控件与月份卡之间要留缝。`.segmented` 只有 margin-top、
   `.card` 没有 margin —— 不补的话控件会跟白卡片贴死。
   （班级页没这个问题，是因为它下面垫了个 44px 高的 .checkbox。同 MineView 的写法） */
.card {
  margin-top: 16px;
}

/* ── 月历网格 ──────────────────────────────────────────
   满宽（左右不留 padding）是为了格子宽度 —— 见「不套 .card」那条注释。
   400px 视口：368 − 12(gap) = 50.9px/格；375px：47.3px；360px：45.1px，
   都还在 44px 触控目标之上。 */
.calendar {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 2px;
  padding: 6px 0;
  border-radius: var(--radius);
  background: var(--color-surface);
  box-shadow: 0 2px 12px rgba(47, 62, 54, 0.06);
  /* 白底 + 圆角下，边格的方角会被切整齐 */
  overflow: hidden;
}

.calendar__weekday {
  padding: 4px 0;
  color: var(--color-text-muted);
  font-size: 12px;
  text-align: center;
}

/* 补位格。留个占位好让 grid 自动排布把日期推到正确的列上 */
.calendar__blank {
  display: block;
}

.calendar__day {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: var(--tap-min);
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text);
  font-size: 14px;
  cursor: pointer;
}

.calendar__day:active {
  background: var(--color-primary-light);
}

/* 那天有课。注意页面底色本身就是 --color-primary-light，
   所以网格必须垫在白底上，否则这一档完全看不出来 */
.calendar__day--has {
  background: var(--color-primary-light);
}

/* 今天：数字着色加粗。和「有课」的底色叠加也不打架 */
.calendar__day--today {
  color: var(--color-primary-dark);
  font-weight: 700;
}

/* 选中：内描边。用 box-shadow 而不是 border —— 不占布局位、不推挤数字，
   而且**没课的那天也看得见**（光靠 --has 的底色是看不出选中的） */
.calendar__day--on {
  box-shadow: inset 0 0 0 2px var(--color-primary-dark);
}

.calendar__num {
  line-height: 1;
}

.calendar__count {
  position: absolute;
  right: 3px;
  bottom: 2px;
  color: var(--color-text-muted);
  font-size: 10px;
  line-height: 1;
}

@media (hover: hover) {
  .calendar__day:hover {
    background: var(--color-primary-light);
  }
}
</style>
