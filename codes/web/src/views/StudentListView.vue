<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { listClasses } from '@/api/classes'
import { listStudents } from '@/api/students'
import AppHeader from '@/components/AppHeader.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const students = ref([])
const classes = ref([])

// 从班级详情跳过来时会带 ?class_id=，直接就把筛选条件带上
const classId = ref(route.query.class_id ? Number(route.query.class_id) : '')
const keyword = ref('')
const showInactive = ref(false)

const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    students.value = await listStudents({
      q: keyword.value.trim(),
      classId: classId.value === '' ? undefined : classId.value,
      isActive: showInactive.value ? undefined : true,
    })
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    classes.value = await listClasses()
  } catch {
    // 班级列表只是筛选下拉的选项，拉不到不影响看学生，
    // 所以这里不设 error —— 为主列表让路，别让用户以为整页都挂了
  }
  await load()
})

watch([classId, showInactive], load)
</script>

<template>
  <div class="page page--top">
    <div class="page__inner">
      <AppHeader title="学生" to="/">
        <template #actions>
          <button
            v-if="auth.isAdmin"
            class="btn btn--sm"
            type="button"
            @click="router.push({ name: 'student-new' })"
          >
            新建
          </button>
        </template>
      </AppHeader>

      <p v-if="error" class="alert">{{ error }}</p>

      <!-- 搜索走 submit 而不是每次敲字都请求：一个是省流量，
           另一个是手机上输入法组字期间会触发一串没意义的中间态查询 -->
      <form class="card" @submit.prevent="load">
        <div class="field">
          <label class="field__label" for="q">搜索</label>
          <input
            id="q"
            v-model="keyword"
            class="field__input"
            type="search"
            placeholder="姓名或手机号"
          />
        </div>

        <div class="field">
          <label class="field__label" for="class">按班级筛选</label>
          <select id="class" v-model="classId" class="field__select">
            <option value="">全部班级</option>
            <option v-for="klass in classes" :key="klass.id" :value="klass.id">
              {{ klass.name }}
            </option>
          </select>
        </div>

        <label class="checkbox">
          <input v-model="showInactive" type="checkbox" />
          <span>显示已停用</span>
        </label>

        <button class="btn" type="submit">搜索</button>
      </form>

      <p v-if="loading" class="hint">加载中…</p>

      <p v-else-if="!students.length" class="empty">没有符合条件的学生</p>

      <div v-else class="list">
        <button
          v-for="student in students"
          :key="student.id"
          class="list__item"
          type="button"
          @click="router.push({ name: 'student-detail', params: { id: student.id } })"
        >
          <div class="row">
            <p class="list__title">{{ student.name }}</p>
            <span v-if="!student.is_active" class="tag tag--muted">已停用</span>
          </div>
          <p class="list__meta">
            剩 <strong>{{ student.remaining_hours }}</strong> 课时
            <template v-if="student.phone"> · {{ student.phone }}</template>
          </p>
        </button>
      </div>
    </div>
  </div>
</template>
