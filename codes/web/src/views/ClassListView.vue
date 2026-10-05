<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { listClasses } from '@/api/classes'
import AppHeader from '@/components/AppHeader.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

const classes = ref([])
const showInactive = ref(false)
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    // 不勾「显示已停用」就只要在册的（is_active=true）；
    // 勾了就连 is_active 都不传，后端返回全部。
    classes.value = await listClasses(showInactive.value ? undefined : true)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(showInactive, load)
</script>

<template>
  <div class="page page--top">
    <div class="page__inner">
      <AppHeader title="班级" to="/">
        <template #actions>
          <button
            v-if="auth.isAdmin"
            class="btn btn--sm"
            type="button"
            @click="router.push({ name: 'class-new' })"
          >
            新建
          </button>
        </template>
      </AppHeader>

      <p v-if="error" class="alert">{{ error }}</p>

      <label class="checkbox">
        <input v-model="showInactive" type="checkbox" />
        <span>显示已停用</span>
      </label>

      <p v-if="loading" class="hint">加载中…</p>

      <p v-else-if="!classes.length" class="empty">还没有班级</p>

      <div v-else class="list">
        <button
          v-for="klass in classes"
          :key="klass.id"
          class="list__item"
          type="button"
          @click="router.push({ name: 'class-detail', params: { id: klass.id } })"
        >
          <div class="row">
            <p class="list__title">{{ klass.name }}</p>
            <span v-if="!klass.is_active" class="tag tag--muted">已停用</span>
          </div>
          <p class="list__meta">
            <span class="tag">{{ klass.class_type }}</span>
            ¥{{ klass.rate }}/课时 · 在册 {{ klass.student_count }} 人
          </p>
        </button>
      </div>
    </div>
  </div>
</template>
