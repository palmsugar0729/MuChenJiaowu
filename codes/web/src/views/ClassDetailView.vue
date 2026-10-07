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
import TabBar from '@/components/TabBar.vue'
import { useAuthStore } from '@/stores/auth'
import { useMetaStore } from '@/stores/meta'
import { formatDate, todayISO } from '@/utils/date'

const auth = useAuthStore()
const meta = useMetaStore()
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

onMounted(async () => {
  // 容量规则来自后端（GET /classes/rules）。拿不到就退化成「不显示上限」，
  // 页面照样能用 —— 真正的闸门在后端，这里只是提前告知，不是把关。
  try {
    await meta.load()
  } catch {
    // 故意吞掉：班级本身还是能看的
  }
  await load()
})

/** 本班在册人数上限；`null` = 认不出的类型，不限制 */
const capacity = computed(() => meta.capacityFor(detail.value?.class_type))

const studentCount = computed(() => detail.value?.student_count ?? 0)

/** 还能再加几个。上限未知时给 Infinity，下面就不用到处写 null 分支 */
const seatsLeft = computed(() => {
  const cap = capacity.value
  return cap === null ? Infinity : cap - studentCount.value
})

const isFull = computed(() => seatsLeft.value <= 0)
const isOverCapacity = computed(() => seatsLeft.value < 0)
/** 超了几个人（没超就是 0），给提示文案用 */
const overBy = computed(() => Math.max(0, -seatsLeft.value))

/** 卡片里那行「在册学生」的文案。上限未知时不写分母 */
const occupancyText = computed(() =>
  capacity.value === null
    ? `${studentCount.value} 人`
    : `${studentCount.value} / ${capacity.value} 人`,
)

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

/** 还能勾吗：已勾的可以取消，没勾的只在还有空位时才能勾。
    到上限后剩下的置灰 —— 比「点了一点反应都没有」清楚。 */
function canPick(id) {
  return selectedIds.value.includes(id) || selectedIds.value.length < seatsLeft.value
}

function togglePick(id) {
  const at = selectedIds.value.indexOf(id)
  if (at >= 0) {
    selectedIds.value.splice(at, 1)
    return
  }
  // 一次最多补满空位。多勾的会被后端整体 400 拒掉（全有或全无），
  // 与其让用户白勾一场，不如当场拦住
  if (!canPick(id)) return
  selectedIds.value.push(id)
}

async function submitAdd() {
  if (!selectedIds.value.length) return

  // 兜底：勾选时已经拦过，但名单可能在打开面板后被人改过
  if (isFull.value || selectedIds.value.length > seatsLeft.value) {
    error.value = `这个班已经满了（在册 ${occupancyText.value}），请先移出学生`
    return
  }

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
  <div class="page page--top page--tabbed">
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
              <span v-else-if="isOverCapacity" class="tag tag--warn">超员</span>
            </div>
            <strong>¥{{ detail.rate }}/课时</strong>
          </div>

          <div class="row">
            <span>在册学生</span>
            <span>{{ occupancyText }}</span>
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
            <button
              class="btn btn--ghost"
              type="button"
              :disabled="isFull"
              @click="openPicker"
            >
              {{ isFull ? '已满员' : '加学生' }}
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

          <!-- 加不进去的原因要说清楚，不然「已满员」的灰按钮只会让人困惑 -->
          <p v-if="!picking && !charging && isOverCapacity" class="hint hint--left">
            「{{ detail.class_type }}」上限 {{ capacity }} 人，而这个班有
            {{ studentCount }} 名在册学生 —— 是上限规则之前建的。请先移出 {{ overBy }} 人。
          </p>
          <p v-else-if="!picking && !charging && isFull" class="hint hint--left">
            「{{ detail.class_type }}」最多 {{ capacity }} 名学生，这个班已经满了。
          </p>

          <div v-if="picking" class="card">
            <p class="section">选择要加入的学生</p>

            <p v-if="capacity !== null" class="field__hint">
              「{{ detail.class_type }}」上限 {{ capacity }} 人，还能再加
              {{ seatsLeft }} 人。
            </p>

            <p v-if="!candidates.length" class="hint">没有可加入的学生了</p>

            <div v-else class="list">
              <label
                v-for="s in candidates"
                :key="s.id"
                class="checkbox"
                :class="{ 'checkbox--off': !canPick(s.id) }"
              >
                <input
                  type="checkbox"
                  :checked="selectedIds.includes(s.id)"
                  :disabled="!canPick(s.id)"
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

    <TabBar />
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
