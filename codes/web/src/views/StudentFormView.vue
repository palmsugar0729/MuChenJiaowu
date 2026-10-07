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
  note: '',
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
        <p v-if="!isEdit && defaultHours > 0" class="field__hint">
          保存后自动送 {{ defaultHours }} 课时，并记一条充值流水。以后续费再手动充。
        </p>

        <button class="btn" type="submit" :disabled="saving">
          {{ saving ? '保存中…' : '保存' }}
        </button>
      </form>
    </div>
  </div>
</template>
