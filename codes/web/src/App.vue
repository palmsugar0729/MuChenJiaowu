<script setup>
// 外壳负责两件事：渲染路由出口 + 挂一个全局唯一的确认框。
// 确认框放在这里（不是每个页面各摆一个），任何页面 `await confirmAction()` 都能用。
import AppDialog from '@/components/AppDialog.vue'
import { answerDialog, dialogState } from '@/composables/confirm'
</script>

<template>
  <RouterView />
  <AppDialog
    v-if="dialogState.open"
    :title="dialogState.title"
    :message="dialogState.message"
    :confirm-text="dialogState.confirmText"
    :cancel-text="dialogState.cancelText"
    :danger="dialogState.danger"
    @confirm="answerDialog(true)"
    @cancel="answerDialog(false)"
  />
</template>
