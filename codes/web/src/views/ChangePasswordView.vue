<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import PasswordField from '@/components/PasswordField.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

// 首次登录被强制进来时，不给退路：不显示返回按钮
const forced = computed(() => auth.mustChangePassword)

const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''

  if (!oldPassword.value || !newPassword.value) {
    error.value = '请填写原密码和新密码'
    return
  }

  // 后端没有确认密码这个字段，两次一致性只能在前端把
  if (newPassword.value !== confirmPassword.value) {
    error.value = '两次输入的新密码不一致'
    return
  }

  loading.value = true
  try {
    await auth.changePassword(oldPassword.value, newPassword.value)
    // 改完 mustChangePassword 变 false，守卫不再改道
    //
    // ⚠️ 这里原来写的是 `{ name: 'home' }` —— 那个路由随「我的」页上线就被删了，
    //    而行没跟着改。vue-router 5 对**不存在的具名路由是抛异常**（不是静默跳过），
    //    于是这个 throw 落进下面的 catch，用户看到一屏红字、人卡在改密页上
    //    （密码其实改成功了，刷新一下就好 —— 所以才特别难查）。
    //    每个首次登录被强制改密的新老师都会撞上。
    router.replace({ name: 'lesson-list' })
  } catch (e) {
    // 后端文案：原密码不正确 / 新密码至少 6 位 / 新密码不能和原密码相同
    error.value = e.message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="page">
    <div class="page__inner">
      <div class="brand">
        <h1 class="brand__title">{{ forced ? '请先修改密码' : '修改密码' }}</h1>
        <p class="brand__sub">
          {{ forced ? '初始密码是系统生成的，请换成只有你自己知道的' : '改完请用新密码重新登录其他设备' }}
        </p>
      </div>

      <form class="card" @submit.prevent="submit">
        <p v-if="error" class="alert">{{ error }}</p>

        <PasswordField
          id="old-password"
          v-model="oldPassword"
          label="原密码"
          autocomplete="current-password"
          placeholder="请输入原密码"
        />

        <PasswordField
          id="new-password"
          v-model="newPassword"
          label="新密码"
          autocomplete="new-password"
          placeholder="至少 6 位"
        />

        <PasswordField
          id="confirm-password"
          v-model="confirmPassword"
          label="确认新密码"
          autocomplete="new-password"
          placeholder="再输一次新密码"
        />

        <button class="btn" type="submit" :disabled="loading">
          {{ loading ? '提交中…' : '确定修改' }}
        </button>
      </form>

      <p v-if="forced" class="hint">首次登录必须修改密码后才能继续</p>
    </div>
  </div>
</template>
