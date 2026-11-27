<script setup>
/**
 * 排课 / 改课（管理员）。新建和编辑复用同一个组件，靠 route.params.id 区分。
 *
 * ⚠️ **没有费率输入框**：费率由后端在排课时从 `classes.rate` 快照一份。
 *    让界面能填费率，等于谁都能给自己开 999 元/时。
 */

import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { listUsers } from '@/api/admin'
import { listClasses } from '@/api/classes'
import { createLesson, createRecurringLessons, getLesson, updateLesson } from '@/api/lessons'
import AppHeader from '@/components/AppHeader.vue'
import { useAuthStore } from '@/stores/auth'
import { formatTime, shiftDays, todayISO } from '@/utils/date'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const lessonId = route.params.id ? Number(route.params.id) : null
const isEdit = computed(() => lessonId !== null)

const form = ref({
  class_id: '',
  teacher_id: '',
  // 从日视图「排课」进来时带上当天，省得再选一次
  date: route.query.date || todayISO(),
  start_time: '09:00',
  /**
   * ★ 时长按「几小时 + 几分钟」填（用户 2026-11-25 定），不再填 1.5 这种小数。
   *   提交时换算成课时 `h + m/60`，由后端舍到两位小数（1 小时 50 分 → 1.83）。
   *   ⚠️ 别在这里自己 `toFixed` 后当课时用 —— 舍入口径只允许有一个（后端）。
   */
  duration_h: 1,
  duration_m: 0,
  note: '',
})

/** 时长换算出来的课时数（未舍入，只用于预览和校验；落库以后端为准） */
const hours = computed(() => {
  const h = Number(form.value.duration_h) || 0
  const m = Number(form.value.duration_m) || 0
  return Math.round((h + m / 60) * 100) / 100
})

/** 「1 小时 45 分」这种人话 */
const durationText = computed(() => {
  const h = Number(form.value.duration_h) || 0
  const m = Number(form.value.duration_m) || 0
  if (h && m) return `${h} 小时 ${m} 分`
  if (h) return `${h} 小时`
  return `${m} 分钟`
})

function pad2(n) {
  return String(n).padStart(2, '0')
}

/**
 * 结束时间 = 开始 + 时长。整天排下来一眼能看出是不是跟下一节撞了。
 * ⚠️ 后端不存结束时间，时间轴那边也是这么现算的（`LessonTimeline.endMin`）。
 */
const endTime = computed(() => {
  const [h, m] = String(form.value.start_time || '00:00').split(':').map(Number)
  const total = (h || 0) * 60 + (m || 0) + Math.round(hours.value * 60)
  return `${pad2(Math.floor(total / 60) % 24)}:${pad2(total % 60)}`
})

/** 这节课会算多少钱（课时 × 班级费率快照），给排课的人一个准头 */
const money = computed(() => {
  const rate = Number(selectedClass.value?.rate) || 0
  return Math.round(hours.value * rate * 100) / 100
})

const classes = ref([])
const teachers = ref([])
const loadedLesson = ref(null)
const loading = ref(true)
const error = ref('')
const busy = ref(false)

/**
 * ★ 连续排课（用户 2026-11-27 定）：勾上之后按「每 7 天一节」把后面几周一起排掉。
 *   编辑已有课程时不出这个选项 —— 改课只改这一节，别把后面几周也顺手改了。
 */
const repeat = ref(false)
const weeks = ref(4)
/** 连排结果（`{ created, skipped }`）。排完停在本页把结果说清楚，别默默跳走 */
const result = ref(null)

/** `11-28` 这种短日期，结果里列出来用 */
function shortDate(iso) {
  return String(iso).slice(5)
}

/** 后端 `MAX_RECURRING_WEEKS` 同一个数，别让它漂 */
const MAX_REPEAT_WEEKS = 52

/** 预览：从选中的那天起，每 7 天一个，共 N 个 */
const repeatDates = computed(() => {
  if (!repeat.value || isEdit.value) return []
  const n = Number(weeks.value) || 0
  if (n < 1 || n > MAX_REPEAT_WEEKS) return []
  return Array.from({ length: n }, (_, i) => shiftDays(form.value.date, i * 7))
})

const selectedClass = computed(
  () => classes.value.find((c) => c.id === Number(form.value.class_id)) || null,
)

/**
 * 小班要凑够 3 个人才排得了课（用户 2026-11-25 定）。
 *
 * ⚠️ 和后端 `core/class_rules` 的 `SMALL_CLASS_TYPES` / `MIN_SMALL_CLASS_STUDENTS`
 *    保持一致。这里只是**提前拦住并说清楚原因**，真相源在后端 —— 前端算错了
 *    也只会吃一个 400 把后端原话显示出来，不会排出一节 1 个人的小班课。
 */
const SMALL_CLASS_TYPES = ['1对3', '1对4', '1对5']
const MIN_SMALL_CLASS_STUDENTS = 3

const smallClassNotReady = computed(() => {
  const klass = selectedClass.value
  if (!klass || !SMALL_CLASS_TYPES.includes(klass.class_type)) return false
  return klass.student_count < MIN_SMALL_CLASS_STUDENTS
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    classes.value = await listClasses(true) // 只列还在用的班
    teachers.value = (await listUsers()).filter((u) => u.is_active)

    if (isEdit.value) {
      const lesson = await getLesson(lessonId)
      if (lesson.status !== 'scheduled') {
        error.value = '只有「已排课」的课程能修改，已上过或已取消的课改不了'
        loadedLesson.value = lesson
        return
      }
      loadedLesson.value = lesson
      // 课时 → 「几小时几分钟」。1.83 课时 = 110 分钟 = 1 小时 50 分
      const totalMinutes = Math.round(lesson.hours * 60)
      form.value = {
        class_id: lesson.class_id,
        teacher_id: lesson.teacher_id,
        date: lesson.lesson_date,
        start_time: formatTime(lesson.start_time),
        duration_h: Math.floor(totalMinutes / 60),
        duration_m: totalMinutes % 60,
        note: lesson.note,
      }
    }
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function submit() {
  if (!isEdit.value && !form.value.class_id) {
    error.value = '请选择班级'
    return
  }
  if (!form.value.teacher_id) {
    error.value = '请选择任课老师'
    return
  }
  if (smallClassNotReady.value) {
    error.value = `这个班只有 ${selectedClass.value.student_count} 名学生，小班要满 ${MIN_SMALL_CLASS_STUDENTS} 人才能排课。请先把学生加进班级`
    return
  }
  const minutes = Number(form.value.duration_m) || 0
  if (minutes < 0 || minutes > 59) {
    error.value = '分钟只能填 0 到 59'
    return
  }
  if (!hours.value) {
    error.value = '上课时长要大于 0'
    return
  }
  if (repeat.value && !isEdit.value) {
    const n = Number(weeks.value)
    if (!Number.isInteger(n) || n < 1 || n > MAX_REPEAT_WEEKS) {
      error.value = `连续排课要填 1 到 ${MAX_REPEAT_WEEKS} 周`
      return
    }
  }

  // ⚠️ <input type="time"> 给的是 HH:MM，后端的 time 字段要 HH:MM:SS
  const common = {
    date: form.value.date,
    start_time: `${form.value.start_time}:00`,
    // 课时 = 时长换算；两位小数的舍入交给后端（口径只留一处）
    hours: hours.value,
    note: form.value.note,
    teacher_id: Number(form.value.teacher_id),
  }

  busy.value = true
  error.value = ''
  try {
    if (isEdit.value) {
      const saved = await updateLesson(lessonId, common)
      router.replace({
        name: 'lesson-detail',
        params: { id: saved.id },
        query: { date: saved.lesson_date },
      })
      return
    }

    if (repeat.value) {
      // 连排：停在本页把结果说清楚（排了几节、跳了哪几周），别默默跳走
      result.value = await createRecurringLessons({
        ...common,
        class_id: Number(form.value.class_id),
        weeks: Number(weeks.value),
      })
      busy.value = false
      return
    }

    const saved = await createLesson({ ...common, class_id: Number(form.value.class_id) })
    router.replace({
      name: 'lesson-detail',
      params: { id: saved.id },
      query: { date: saved.lesson_date },
    })
  } catch (e) {
    error.value = e.message
    busy.value = false
  }
}

/** 连排完之后：去第一天（或第一节建成的课）的课表 */
function goToResult() {
  const first = result.value.created[0] || { lesson_date: form.value.date }
  router.replace({ name: 'lesson-list', query: { date: first.lesson_date } })
}

/** 接着排下一批：清掉结果，表单内容留着改 */
function resetResult() {
  result.value = null
}
</script>

<template>
  <div class="page page--top">
    <div class="page__inner">
      <AppHeader :title="isEdit ? '改课' : '排课'" to="/lessons" />

      <p v-if="error" class="alert">{{ error }}</p>
      <p v-if="loading" class="hint">加载中…</p>

      <p v-else-if="!auth.isAdmin" class="empty">只有管理员能排课</p>

      <p v-else-if="loadedLesson && loadedLesson.status !== 'scheduled'" class="empty">
        只有「已排课」的课程能修改。
        <br />
        已上过的课请先「取消课程」（课时会退回），再重新排一节。
      </p>

      <template v-else>
        <div class="card">
          <div v-if="isEdit" class="field">
            <span class="field__label">班级</span>
            <p class="list__title">{{ loadedLesson?.class_name }}</p>
            <p class="field__hint">换班请取消这节课后重新排 —— 费率快照是按班级定的。</p>
          </div>

          <div v-else class="field">
            <label class="field__label" for="class">班级</label>
            <select id="class" v-model="form.class_id" class="field__select">
              <option value="">请选择</option>
              <option v-for="c in classes" :key="c.id" :value="c.id">
                {{ c.name }}（{{ c.class_type }} · {{ c.student_count }} 人）
              </option>
            </select>
            <p v-if="smallClassNotReady" class="field__error">
              这个班只有 {{ selectedClass.student_count }} 名学生，小班要满
              {{ MIN_SMALL_CLASS_STUDENTS }} 人才能排课 —— 请先到班级页把学生加进去。
            </p>
            <p v-if="selectedClass" class="field__hint">
              费率由班级决定（¥{{ selectedClass.rate }}/时），排课时自动快照 ——
              以后改班级费率不影响这节课。
            </p>
          </div>

          <div class="field">
            <label class="field__label" for="teacher">任课老师</label>
            <select id="teacher" v-model="form.teacher_id" class="field__select">
              <option value="">请选择</option>
              <option v-for="u in teachers" :key="u.id" :value="u.id">
                {{ u.display_name }}
              </option>
            </select>
          </div>

          <div class="field">
            <label class="field__label" for="date">上课日期</label>
            <input id="date" v-model="form.date" class="field__input" type="date" />
          </div>

          <div class="field">
            <label class="field__label" for="start">上课时间</label>
            <input id="start" v-model="form.start_time" class="field__input" type="time" />
          </div>

          <!-- 时长按「小时 + 分钟」填（用户 2026-11-25 定），不再填 1.5 这种小数 -->
          <div class="field__pair">
            <div class="field">
              <label class="field__label" for="dur-h">上多久 · 小时</label>
              <input
                id="dur-h"
                v-model="form.duration_h"
                class="field__input"
                type="number"
                inputmode="numeric"
                min="0"
                max="12"
                step="1"
              />
            </div>

            <div class="field">
              <label class="field__label" for="dur-m">· 分钟</label>
              <input
                id="dur-m"
                v-model="form.duration_m"
                class="field__input"
                type="number"
                inputmode="numeric"
                min="0"
                max="59"
                step="1"
              />
            </div>
          </div>

          <p class="field__hint">
            {{ form.start_time }} 开始，上 {{ durationText }} → <strong>{{ endTime }} 结束</strong>
            · 记 {{ hours }} 课时<template v-if="selectedClass">（¥{{ money }}）</template>
          </p>

          <div class="field">
            <label class="field__label" for="note">备注</label>
            <input
              id="note"
              v-model="form.note"
              class="field__input"
              type="text"
              placeholder="选填"
            />
          </div>

          <!-- ★ 连续排课（用户 2026-11-27 定）。编辑已有课程时不出 —— 改课只改这一节 -->
          <template v-if="!isEdit">
            <label class="checkbox">
              <input v-model="repeat" type="checkbox" />
              <span>连续排课（每周同一时间自动往下排）</span>
            </label>

            <div v-if="repeat" class="field">
              <label class="field__label" for="weeks">连续排几周</label>
              <input
                id="weeks"
                v-model="weeks"
                class="field__input"
                type="number"
                inputmode="numeric"
                min="1"
                :max="MAX_REPEAT_WEEKS"
                step="1"
              />
              <p v-if="repeatDates.length" class="field__hint">
                共 {{ repeatDates.length }} 节：{{ repeatDates.map(shortDate).join('、') }}
              </p>
              <p v-else class="field__hint">周数要填 1 到 {{ MAX_REPEAT_WEEKS }}</p>
              <p class="field__hint">
                某一周同一时间已经有这个班的课，那一周自动跳过，排完会告诉你跳了哪几周。
              </p>
            </div>
          </template>

          <button
            v-if="!result"
            class="btn"
            type="button"
            :disabled="busy || (!isEdit && smallClassNotReady) || !hours"
            @click="submit"
          >
            {{ isEdit ? '保存' : repeat ? '连续排课' : '排课' }}
          </button>
        </div>

        <!-- 连排结果：排了哪几周、哪几周因为已有同样的课被跳过 -->
        <div v-if="result" class="card">
          <p class="notice">
            已排 <strong>{{ result.created.length }}</strong> 节：
            {{ result.created.map((l) => shortDate(l.lesson_date)).join('、') || '（一节都没排）' }}
          </p>
          <p v-if="result.skipped.length" class="field__hint">
            跳过 {{ result.skipped.length }} 节：{{ result.skipped.map(shortDate).join('、') }}
            —— 那一周同一时间已经有这个班的课了
          </p>

          <div class="toolbar">
            <button v-if="result.created.length" class="btn" type="button" @click="goToResult">
              去课表
            </button>
            <button class="btn btn--ghost" type="button" @click="resetResult">再排一批</button>
          </div>
        </div>

        <p v-if="!result" class="hint">
          排课只是安排，<strong>不扣课时</strong>。上完课在详情页点「完成上课」才扣。
        </p>
      </template>
    </div>
  </div>
</template>
