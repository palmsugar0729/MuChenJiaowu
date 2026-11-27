<script setup>
/**
 * 学生表单 —— 新建和编辑复用，靠路由里有没有 `id` 区分。
 *
 * 学生**不是账号**，永远不会登录，所以这里没有角色、密码之类的东西。
 * 手机上填表以少为主：只有姓名是必填，其余都能留空以后补。
 */

import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { createStudent, getStudent, updateStudent } from '@/api/students'
import AppHeader from '@/components/AppHeader.vue'
import { useMetaStore } from '@/stores/meta'

const route = useRoute()
const router = useRouter()
const meta = useMetaStore()

/** 建档时后端会自动送多少课时。取自后端，不在页面里写死。 */
const defaultHours = computed(() => meta.defaultStudentHours)

const studentId = route.params.id ? Number(route.params.id) : null
const isEdit = studentId !== null

// is_adult 是三态：true / false / 未知(null)。下拉里用字符串表达，
// 提交前再转回布尔或 null —— 直接把 null 绑到 select 的 value 会变成 "null"。
const form = ref({
  name: '',
  gender: '',
  is_adult: '',
  phone: '',
  // 学生级别 N1~N5，空串 = 没填
  level: '',
  note: '',
})

/**
 * ★ 2026-11-27 用户定：级别决定**建档时**送多少课时
 * （N1=60、N2=55、N3/N4=51、N5=48、不填=48）。
 * 映射从 `/classes/rules` 拿，别在这儿抄常量；拿不到就退回默认数。
 * ⚠️ **只在建档时有意义**：编辑时改级别不补也不扣课时（后端定的）。
 */
const initialHours = computed(() => {
  const map = meta.levelHours
  return map[form.value.level] ?? defaultHours.value
})

const loading = ref(true)
const saving = ref(false)
const error = ref('')

onMounted(async () => {
  // 只是为了让「保存后送 N 课时」那行有数字。**拿不到不影响建档** ——
  // 提示不显示而已，后端该送的照送，所以失败也不用管。
  meta.load().catch(() => {})

  if (!isEdit) {
    loading.value = false
    return
  }

  try {
    const detail = await getStudent(studentId)
    form.value = {
      name: detail.name,
      gender: detail.gender || '',
      is_adult: detail.is_adult === null ? '' : String(detail.is_adult),
      phone: detail.phone || '',
      level: detail.level || '',
      note: detail.note || '',
    }
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

async function submit() {
  error.value = ''

  if (!form.value.name.trim()) {
    error.value = '请填写学生姓名'
    return
  }

  const payload = {
    name: form.value.name.trim(),
    gender: form.value.gender,
    // 空串 = 没填 = null，别把 '' 传过去（后端的 bool | None 收不了）
    is_adult: form.value.is_adult === '' ? null : form.value.is_adult === 'true',
    phone: form.value.phone.trim() || null,
    // 空串 = 没填级别（后端当 null，按默认 48 课时）
    level: form.value.level || null,
    note: form.value.note.trim(),
  }

  saving.value = true
  try {
    const saved = isEdit
      ? await updateStudent(studentId, payload)
      : await createStudent(payload)
    router.replace({ name: 'student-detail', params: { id: saved.id } })
  } catch (e) {
    error.value = e.message
    saving.value = false
  }
}
</script>

<template>
  <div class="page page--top">
    <div class="page__inner">
      <AppHeader
        :title="isEdit ? '编辑学生' : '新建学生'"
        :to="isEdit ? `/students/${studentId}` : '/students'"
      />

      <p v-if="error" class="alert">{{ error }}</p>
      <p v-if="loading" class="hint">加载中…</p>

      <form v-else class="card" @submit.prevent="submit">
        <div class="field">
          <label class="field__label" for="name">姓名</label>
          <input
            id="name"
            v-model="form.name"
            class="field__input"
            type="text"
            placeholder="学生姓名"
          />
        </div>

        <div class="field__pair">
          <div class="field">
            <label class="field__label" for="gender">性别</label>
            <select id="gender" v-model="form.gender" class="field__select">
              <option value="">未填</option>
              <option value="男">男</option>
              <option value="女">女</option>
            </select>
          </div>

          <div class="field">
            <label class="field__label" for="adult">是否成年</label>
            <select id="adult" v-model="form.is_adult" class="field__select">
              <option value="">未填</option>
              <option value="true">是</option>
              <option value="false">否</option>
            </select>
          </div>
        </div>

        <!-- ★ 级别决定建档送多少课时（用户 2026-11-27 定）。
             编辑时只是改标签 —— 课时不会因为改级别而变动，得说清楚 -->
        <div class="field">
          <label class="field__label" for="level">级别</label>
          <select id="level" v-model="form.level" class="field__select">
            <option value="">未填（自动加 {{ defaultHours }} 课时）</option>
            <option v-for="lv in meta.levels" :key="lv" :value="lv">
              {{ lv }}（自动加 {{ meta.levelHours[lv] }} 课时）
            </option>
          </select>
          <p v-if="isEdit" class="field__hint">
            改级别只是个标签 —— <strong>不会补课时，也不会扣课时</strong>。
          </p>
        </div>

        <div class="field">
          <label class="field__label" for="phone">手机号</label>
          <input
            id="phone"
            v-model="form.phone"
            class="field__input"
            type="tel"
            inputmode="numeric"
            placeholder="可留空 —— 学生不用登录，这只是联系方式"
          />
        </div>

        <div class="field">
          <label class="field__label" for="note">备注</label>
          <input
            id="note"
            v-model="form.note"
            class="field__input"
            type="text"
            placeholder="可留空"
          />
        </div>

        <!-- ★ 建档会**真的送课时**（记一条 purchase 流水，不是塞个初值），
             所以必须提前说一声，不能建完了让人在流水里自己发现。
             编辑时不显示 —— 那是改资料，不送课时。 -->
        <p v-if="!isEdit && initialHours > 0" class="field__hint">
          保存后自动加上根据级别而定的课时，并记一条加课时流水（固定操作，不可更改）。以后续费再手动加。
        </p>

        <button class="btn" type="submit" :disabled="saving">
          {{ saving ? '保存中…' : '保存' }}
        </button>
      </form>
    </div>
  </div>
</template>
