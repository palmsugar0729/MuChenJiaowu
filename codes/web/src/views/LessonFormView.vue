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
import { createLesson, getLesson, updateLesson } from '@/api/lessons'
import AppHeader from '@/components/AppHeader.vue'
import { useAuthStore } from '@/stores/auth'
import { formatTime, todayISO } from '@/utils/date'

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
  hours: 1,
  note: '',
})

const classes = ref([])
const teachers = ref([])
const loadedLesson = ref(null)
const loading = ref(true)
const error = ref('')
const busy = ref(false)

const selectedClass = computed(
  () => classes.value.find((c) => c.id === Number(form.value.class_id)) || null,
)

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
      form.value = {
        class_id: lesson.class_id,
        teacher_id: lesson.teacher_id,
        date: lesson.lesson_date,
        start_time: formatTime(lesson.start_time),
        hours: lesson.hours,
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
  const hours = Number(form.value.hours)
  if (!hours || hours <= 0) {
    error.value = '课时必须大于 0'
    return
  }

  // ⚠️ <input type="time"> 给的是 HH:MM，后端的 time 字段要 HH:MM:SS
  const common = {
    date: form.value.date,
    start_time: `${form.value.start_time}:00`,
    hours,
    note: form.value.note,
    teacher_id: Number(form.value.teacher_id),
  }

  busy.value = true
  error.value = ''
  try {
    const saved = isEdit.value
      ? await updateLesson(lessonId, common) // 编辑时不能换班，也不发 class_id
      : await createLesson({ ...common, class_id: Number(form.value.class_id) })

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

          <div class="field__pair">
            <div class="field">
              <label class="field__label" for="start">开始时间</label>
              <input id="start" v-model="form.start_time" class="field__input" type="time" />
            </div>

            <div class="field">
              <label class="field__label" for="hours">课时（小时）</label>
              <input
                id="hours"
                v-model="form.hours"
                class="field__input"
                type="number"
                inputmode="decimal"
                min="0"
                step="0.5"
              />
            </div>
          </div>

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

          <button class="btn" type="button" :disabled="busy" @click="submit">
            {{ isEdit ? '保存' : '排课' }}
          </button>
        </div>

        <p class="hint">
          排课只是安排，<strong>不扣课时</strong>。上完课在详情页点「完成上课」才扣。
        </p>
      </template>
    </div>
  </div>
</template>
