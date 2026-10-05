<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  addClassStudents,
  deleteClass,
  getClass,
  listClassStudents,
  removeClassStudent,
  updateClass,
} from '@/api/classes'
import { batchAddHours, listStudents } from '@/api/students'
import AppHeader from '@/components/AppHeader.vue'
import { useAuthStore } from '@/stores/auth'
import { formatDate, todayISO } from '@/utils/date'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const classId = Number(route.params.id)

const detail = ref(null)
const loading = ref(true)
const error = ref('')
/** 操作反馈（加了学生、充了课时），跟 error 分开显示 */
const notice = ref('')
const busy = ref(false)

/** 加学生面板 */
const picking = ref(false)
const candidates = ref([])
const selectedIds = ref([])

/** 全班充课时面板 */
const charging = ref(false)
const chargeAmount = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    detail.value = await getClass(classId)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(load)

/** 在册学生的 id 集合 —— 候选名单要把它排掉 */
const memberIds = computed(
  () => new Set((detail.value?.students || []).map((s) => s.student_id)),
)

/** 手动刷新在册名单。用 listClassStudents 而不是重拉整个详情，
    避免把用户正在编辑的面板状态一起重置掉。 */
async function reloadStudents() {
  const rows = await listClassStudents(classId)
  if (detail.value) {
    detail.value.students = rows
    detail.value.student_count = rows.length
  }
}

async function openPicker() {
  error.value = ''
  notice.value = ''
  picking.value = true
  selectedIds.value = []
  try {
    // 后端返回的在册学生里可能已经有人在这个班了，这里按 id 排掉
    const all = await listStudents({ isActive: true })
    candidates.value = all.filter((s) => !memberIds.value.has(s.id))
  } catch (e) {
    error.value = e.message
    picking.value = false
  }
}

function togglePick(id) {
  const at = selectedIds.value.indexOf(id)
  if (at >= 0) selectedIds.value.splice(at, 1)
  else selectedIds.value.push(id)
}

async function submitAdd() {
  if (!selectedIds.value.length) return

  busy.value = true
  error.value = ''
  try {
    await addClassStudents(classId, selectedIds.value, todayISO())
    await reloadStudents()
    notice.value = `已加入 ${selectedIds.value.length} 名学生`
    picking.value = false
  } catch (e) {
    // 全有或全无：这里失败就是一个人都没加进去，名单不用刷新
    error.value = e.message
  } finally {
    busy.value = false
  }
}

async function removeStudent(student) {
  if (!window.confirm(`把「${student.name}」移出这个班？\n（只是退班，学生和课时流水都保留）`)) {
    return
  }

  error.value = ''
  try {
    await removeClassStudent(classId, student.student_id)
    await reloadStudents()
    notice.value = `已把「${student.name}」移出班级`
  } catch (e) {
    error.value = e.message
  }
}

async function submitCharge() {
  const amount = Number(chargeAmount.value)
  if (!amount || amount <= 0) {
    error.value = '充值金额必须大于 0'
    return
  }

  busy.value = true
  error.value = ''
  try {
    const rows = await batchAddHours({
      student_ids: detail.value.students.map((s) => s.student_id),
      amount,
      note: `整班充值（${detail.value.name}）`,
    })
    await reloadStudents()
    notice.value = `已给 ${rows.length} 名学生各充 ${amount} 课时`
    charging.value = false
    chargeAmount.value = ''
  } catch (e) {
    // 全有或全无：失败就是一条都没写
    error.value = e.message
  } finally {
    busy.value = false
  }
}

/** 停用 / 启用。停用走 PATCH，**不是** DELETE —— 那才是真删。 */
async function toggleActive() {
  error.value = ''
  try {
    detail.value = {
      ...detail.value,
      ...(await updateClass(classId, { is_active: !detail.value.is_active })),
    }
    notice.value = detail.value.is_active ? '已启用' : '已停用'
  } catch (e) {
    error.value = e.message
  }
}

async function removeClass() {
  if (
    !window.confirm(
      `确定删除班级「${detail.value.name}」？\n` +
        '这是真删，在册关系会一起清掉，不能恢复。\n' +
        '（只是不想再用的话，请改用「停用」）',
    )
  ) {
    return
  }

  busy.value = true
  error.value = ''
  try {
    await deleteClass(classId)
    router.replace({ name: 'class-list' })
  } catch (e) {
    error.value = e.message
    busy.value = false
  }
}
</script>

<template>
  <div class="page page--top">
    <div class="page__inner">
      <AppHeader :title="detail?.name || '班级'" to="/classes">
        <template #actions>
          <button
            v-if="auth.isAdmin && detail"
            class="btn btn--sm btn--ghost"
            type="button"
            @click="router.push({ name: 'class-edit', params: { id: classId } })"
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
            <div>
              <span class="tag">{{ detail.class_type }}</span>
              <span v-if="!detail.is_active" class="tag tag--muted">已停用</span>
            </div>
            <strong>¥{{ detail.rate }}/课时</strong>
          </div>

          <div class="row">
            <span>在册学生</span>
            <span>{{ detail.student_count }} 人</span>
          </div>

          <div class="row">
            <span>累计已上课时</span>
            <span>{{ detail.total_hours }}</span>
          </div>

          <p v-if="detail.note" class="list__meta">{{ detail.note }}</p>
        </div>

        <!-- 加学生（管理员） -->
        <template v-if="auth.isAdmin">
          <div v-if="!picking && !charging" class="toolbar">
            <button class="btn btn--ghost" type="button" @click="openPicker">
              加学生
            </button>
            <button
              class="btn btn--ghost"
              type="button"
              :disabled="!detail.student_count"
              @click="charging = true"
            >
              全班充课时
            </button>
          </div>

          <div v-if="picking" class="card">
            <p class="section">选择要加入的学生</p>

            <p v-if="!candidates.length" class="hint">没有可加入的学生了</p>

            <div v-else class="list">
              <label v-for="s in candidates" :key="s.id" class="checkbox">
                <input
                  type="checkbox"
                  :checked="selectedIds.includes(s.id)"
                  @change="togglePick(s.id)"
                />
                <span>{{ s.name }}（剩 {{ s.remaining_hours }} 课时）</span>
              </label>
            </div>

            <div class="toolbar">
              <button
                class="btn"
                type="button"
                :disabled="busy || !selectedIds.length"
                @click="submitAdd"
              >
                加入（{{ selectedIds.length }}）
              </button>
              <button class="btn btn--ghost" type="button" @click="picking = false">
                取消
              </button>
            </div>
          </div>

          <div v-if="charging" class="card">
            <p class="section">给全班 {{ detail.student_count }} 人统一充课时</p>

            <div class="field">
              <label class="field__label" for="charge">每人的课时数</label>
              <input
                id="charge"
                v-model="chargeAmount"
                class="field__input"
                type="number"
                inputmode="decimal"
                min="0"
                step="0.5"
                placeholder="例如 10"
              />
              <p class="field__hint">
                一次给全班在册学生各充同样课时。有一条失败就一条都不写。
              </p>
            </div>

            <div class="toolbar">
              <button class="btn" type="button" :disabled="busy" @click="submitCharge">
                确认充值
              </button>
              <button class="btn btn--ghost" type="button" @click="charging = false">
                取消
              </button>
            </div>
          </div>
        </template>

        <!-- 在册学生 -->
        <p class="section">在册学生</p>

        <p v-if="!detail.students.length" class="empty">这个班还没有学生</p>

        <div v-else class="list">
          <div v-for="s in detail.students" :key="s.student_id" class="list__item">
            <div class="row">
              <button
                class="link"
                type="button"
                @click="
                  router.push({ name: 'student-detail', params: { id: s.student_id } })
                "
              >
                {{ s.name }}
              </button>
              <strong>剩 {{ s.remaining_hours }} 课时</strong>
            </div>
            <p class="list__meta">入班 {{ formatDate(s.joined_on) }}</p>

            <div v-if="auth.isAdmin" class="toolbar">
              <button
                class="btn btn--sm btn--ghost"
                type="button"
                @click="removeStudent(s)"
              >
                移出班级
              </button>
            </div>
          </div>
        </div>

        <template v-if="auth.isAdmin">
          <div class="toolbar">
            <button class="btn btn--ghost" type="button" :disabled="busy" @click="toggleActive">
              {{ detail.is_active ? '停用班级' : '启用班级' }}
            </button>
          </div>

          <div class="toolbar">
            <button
              class="btn btn--ghost"
              type="button"
              :disabled="busy || detail.has_lessons"
              @click="removeClass"
            >
              删除班级
            </button>
          </div>

          <p v-if="detail.has_lessons" class="hint">
            这个班已经排过课，删不掉（删了那些课就成了孤儿，工资表追溯不回去）。
            不想再用请点「停用班级」。
          </p>
        </template>
      </template>
    </div>
  </div>
</template>

<style scoped>
/* 卡片里的「按钮样」文字链接。用 <button> 是为了键盘/无障碍，样式做扁 */
.link {
  padding: 0;
  border: none;
  background: none;
  color: var(--color-text);
  font-size: 16px;
  font-weight: 600;
  text-decoration: underline;
  text-decoration-color: var(--color-border);
  text-underline-offset: 3px;
  cursor: pointer;
}
</style>
