<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  addStudentHours,
  deactivateStudent,
  getStudent,
  updateStudent,
} from '@/api/students'
import AppHeader from '@/components/AppHeader.vue'
import TabBar from '@/components/TabBar.vue'
import { useAuthStore } from '@/stores/auth'
import { formatDateTime } from '@/utils/date'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const studentId = Number(route.params.id)

const detail = ref(null)
const loading = ref(true)
const error = ref('')
const notice = ref('')
const busy = ref(false)

/** 记账面板。默认「充值」—— 那是 99% 的用法，调整是纠错才用的。 */
const charging = ref(false)
const form = ref({ type: 'purchase', amount: '', note: '' })

const TXN_LABELS = {
  purchase: '充值',
  consume: '上课扣除',
  adjust: '调整',
}

const isAdjust = computed(() => form.value.type === 'adjust')

async function load() {
  loading.value = true
  error.value = ''
  try {
    detail.value = await getStudent(studentId)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(load)

function openCharge() {
  charging.value = true
  error.value = ''
  notice.value = ''
  form.value = { type: 'purchase', amount: '', note: '' }
}

async function submitCharge() {
  error.value = ''

  const amount = Number(form.value.amount)
  if (!form.value.amount || !Number.isFinite(amount) || amount === 0) {
    error.value = isAdjust.value ? '请填写调整数量' : '请填写充值数量'
    return
  }
  if (!isAdjust.value && amount < 0) {
    error.value = '充值数量必须大于 0'
    return
  }
  // 后端也拦（400），这里先拦一道，省得白跑一趟还看不清是哪个字段的错
  if (isAdjust.value && !form.value.note.trim()) {
    error.value = '调整必须填写备注（说清为什么要改）'
    return
  }

  busy.value = true
  try {
    await addStudentHours(studentId, {
      type: form.value.type,
      amount,
      note: form.value.note.trim(),
    })
    await load()
    notice.value = isAdjust.value ? '已调整课时' : `已充值 ${amount} 课时`
    charging.value = false
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

/**
 * 停用 / 启用。
 *
 * ⚠️ 两条路走的是**不同接口**：停用是 `DELETE`（后端语义是软删），
 *    启用只能走 `PATCH is_active=true` —— 没有 `DELETE` 的反操作。
 */
async function toggleActive() {
  const turningOff = detail.value.is_active

  if (turningOff) {
    if (
      !window.confirm(
        `确定停用「${detail.value.name}」？\n` +
          '停用后不会再出现在默认名单里，但资料和课时流水都保留着。',
      )
    ) {
      return
    }
  }

  error.value = ''
  try {
    if (turningOff) await deactivateStudent(studentId)
    else await updateStudent(studentId, { is_active: true })

    await load()
    notice.value = turningOff ? '已停用' : '已启用'
  } catch (e) {
    error.value = e.message
  }
}

/** 金额显示：负数带减号，正数补个 +，一眼看出是进还是出 */
function signed(amount) {
  return amount > 0 ? `+${amount}` : String(amount)
}
</script>

<template>
  <div class="page page--top page--tabbed">
    <div class="page__inner">
      <AppHeader :title="detail?.name || '学生'" to="/students">
        <template #actions>
          <button
            v-if="auth.isAdmin && detail"
            class="btn btn--sm btn--ghost"
            type="button"
            @click="router.push({ name: 'student-edit', params: { id: studentId } })"
          >
            编辑
          </button>
        </template>
      </AppHeader>

      <p v-if="error" class="alert">{{ error }}</p>
      <p v-if="notice" class="notice">{{ notice }}</p>
      <p v-if="loading" class="hint">加载中…</p>

      <template v-else-if="detail">
        <div class="card">
          <div class="row">
            <span>剩余课时</span>
            <strong class="balance">{{ detail.remaining_hours }}</strong>
          </div>
          <div class="row">
            <span>性别</span>
            <span>{{ detail.gender || '—' }}</span>
          </div>
          <div class="row">
            <span>是否成年</span>
            <span>{{ detail.is_adult === null ? '—' : detail.is_adult ? '是' : '否' }}</span>
          </div>
          <div class="row">
            <span>手机号</span>
            <span>{{ detail.phone || '—' }}</span>
          </div>
          <div class="row">
            <span>状态</span>
            <span>
              <span v-if="!detail.is_active" class="tag tag--muted">已停用</span>
              <span v-else class="tag">在册</span>
            </span>
          </div>
          <p v-if="detail.note" class="list__meta">{{ detail.note }}</p>
        </div>

        <div v-if="auth.isAdmin && !charging" class="toolbar">
          <button class="btn" type="button" @click="openCharge">充值 / 调整</button>
        </div>

        <div v-if="charging" class="card">
          <div class="field">
            <label class="field__label" for="type">类型</label>
            <select id="type" v-model="form.type" class="field__select">
              <option value="purchase">充值</option>
              <option value="adjust">调整</option>
            </select>
            <p class="field__hint">
              <template v-if="isAdjust">
                纠错用的，可正可负，必须写清原因。
              </template>
              <template v-else> 买课时。扣课时不在这里，走「完成上课」。 </template>
            </p>
          </div>

          <div class="field">
            <label class="field__label" for="amount">数量</label>
            <input
              id="amount"
              v-model="form.amount"
              class="field__input"
              type="number"
              inputmode="decimal"
              step="0.5"
              :placeholder="isAdjust ? '可为负数，例如 -2' : '例如 10'"
            />
          </div>

          <div class="field">
            <label class="field__label" for="note">
              备注{{ isAdjust ? '（必填）' : '' }}
            </label>
            <input
              id="note"
              v-model="form.note"
              class="field__input"
              type="text"
              placeholder="可留空"
            />
          </div>

          <div class="toolbar">
            <button class="btn" type="button" :disabled="busy" @click="submitCharge">
              确认
            </button>
            <button class="btn btn--ghost" type="button" @click="charging = false">
              取消
            </button>
          </div>
        </div>

        <!-- 所属班级 -->
        <p class="section">所属班级</p>

        <p v-if="!detail.classes.length" class="empty">还没有加入任何班级</p>

        <div v-else class="list">
          <button
            v-for="klass in detail.classes"
            :key="klass.id"
            class="list__item"
            type="button"
            @click="router.push({ name: 'class-detail', params: { id: klass.id } })"
          >
            <div class="row">
              <p class="list__title">{{ klass.name }}</p>
              <span class="tag">{{ klass.class_type }}</span>
            </div>
            <p class="list__meta">¥{{ klass.rate }}/课时</p>
          </button>
        </div>

        <!-- 出勤统计 -->
        <p class="section">出勤统计</p>

        <div class="stats">
          <div class="stat">
            <div class="stat__value">{{ detail.attendance.present }}</div>
            <div class="stat__label">出勤</div>
          </div>
          <div class="stat">
            <div class="stat__value">{{ detail.attendance.leave }}</div>
            <div class="stat__label">请假</div>
          </div>
          <div class="stat">
            <div class="stat__value">{{ detail.attendance.absent }}</div>
            <div class="stat__label">缺勤</div>
          </div>
        </div>
        <p class="hint">
          出勤、请假、缺勤都扣课时，只有课程取消才不扣 —— 这三个数只做统计，
          不影响余额。
        </p>

        <!-- 课时流水 -->
        <p class="section">课时流水</p>

        <p v-if="!detail.transactions.length" class="empty">还没有任何流水</p>

        <div v-else class="list">
          <div v-for="txn in detail.transactions" :key="txn.id" class="list__item">
            <div class="row">
              <span>
                <span class="tag">{{ TXN_LABELS[txn.type] || txn.type }}</span>
              </span>
              <strong class="amount" :class="{ 'amount--out': txn.amount < 0 }">
                {{ signed(txn.amount) }}
              </strong>
            </div>
            <p class="list__meta">
              {{ formatDateTime(txn.created_at) }}
              <template v-if="txn.note"> · {{ txn.note }}</template>
            </p>
          </div>
        </div>

        <template v-if="auth.isAdmin">
          <div class="toolbar">
            <button class="btn btn--ghost" type="button" @click="toggleActive">
              {{ detail.is_active ? '停用学生' : '启用学生' }}
            </button>
          </div>
          <p class="hint">
            停用是软删：资料和课时流水都留着，以后还能查，也能再启用回来。
          </p>
        </template>
      </template>
    </div>

    <TabBar />
  </div>
</template>

<style scoped>
/* 余额 / 流水金额：比正文重一档，扫一眼就能看到 */
.balance,
.amount {
  font-size: 18px;
}

/* 扣课时。用 danger 那组「深字」而不是新引一个红色相 */
.amount--out {
  color: var(--color-danger-text);
}
</style>
