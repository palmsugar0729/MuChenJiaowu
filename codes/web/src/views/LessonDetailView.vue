<script setup>
/**
 * 课程详情 + 考勤。老师的主流程页面。
 *
 * 三种状态对应三套按钮：
 *   scheduled  → 「完成上课」（勾好的考勤跟着一起提交，扣课时）
 *   completed  → 「保存考勤」（事后补改，**课时跟着重算**）
 *   cancelled  → 只读
 *
 * ★ 上课内容（「这节课上到哪了」）**必填**，老师 2026-10-05 定的。
 *   它和排课时的 note 是两回事：note 是排课时写的，content 是上完课写的。
 *
 * ★ 谁被扣课时**看班型**（不是看出勤）：1对1 / 1对2 只有「出勤」的扣
 *   （学生自己买的课时，上几次扣几次），其他班型开课就扣全员、请假缺勤照样扣。
 *   所以每行都标了「扣 / 不扣」，老师点「完成上课」之前就该知道自己这一勾值多少钱。
 *
 * 权限：老师只能碰自己的课（后端也会独立拦 403），管理员全都能做。
 *
 * ★ 老师改期走**审批**（2026-10-10 加的）：提申请 → 管理员通过 → 时间才真的变。
 *   `ApprovalListView` 是管理员那一侧，老师这一侧就在本页就地显示状态 + 撤回。
 *   后端**故意没有** `/approvals/my` —— 老师提申请时本来就在这一页。
 */

import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { withdrawApproval } from '@/api/approvals'
import {
  cancelLesson,
  completeLesson,
  deleteLesson,
  getLesson,
  rescheduleLesson,
  submitAttendance,
} from '@/api/lessons'
import AppHeader from '@/components/AppHeader.vue'
import TabBar from '@/components/TabBar.vue'
import { useAuthStore } from '@/stores/auth'
import {
  formatDate,
  formatDateTime,
  formatTime,
  todayISO,
  weekdayLabel,
} from '@/utils/date'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const lessonId = Number(route.params.id)

const STATUS_LABELS = {
  scheduled: '已排课',
  completed: '已完成',
  cancelled: '已取消',
}

const STATUS_CLASSES = {
  scheduled: '',
  completed: 'tag--solid',
  cancelled: 'tag--muted',
}

const ATTENDANCE_OPTIONS = [
  { value: 'present', label: '出勤' },
  { value: 'leave', label: '请假' },
  { value: 'absent', label: '缺勤' },
]

/** ⚠️ 和后端 `core/class_rules` 的 `PER_STUDENT_HOURS_TYPES` 保持一致。
    这里只用来**即时反馈**（标「不扣课时」、算确认框里的话术），
    真相源在后端 —— 口径不一致也只会显示错，不会扣错钱。

    ★ 2026-10-07 用户把 1对2 也归进这一档：「对于 1对1 和 1对2 的学生来说，
      他买多少课时就是多少……上课了就扣课时，没上就不扣。」 */
const PER_STUDENT_HOURS_TYPES = ['1对1', '1对2']

const detail = ref(null)
const loading = ref(true)
const error = ref('')
const notice = ref('')
const busy = ref(false)

/** 本地勾选：student_id → 'present' | 'leave' | 'absent' */
const marks = ref({})

/** ★ 上课内容。完成上课必填，事后改考勤时可以顺手改它。 */
const content = ref('')

/** 本人老师或管理员才能操作这节课。 */
const canOperate = computed(
  () => !!detail.value && (auth.isAdmin || detail.value.teacher_id === auth.user?.id),
)

/**
 * ★ 还没到的课不能做考勤（用户 2026-10-29 定的）：人还没上课，点名、扣课时
 *   都是凭空记账。要改时间走「申请改期」。
 *
 * ⚠️ 用 `todayISO()` 按**本地时间**取今天，别写 `toISOString().slice(0, 10)`
 *    （UTC 日期，中国早上 8 点前会取到昨天，今天的课就被当成未来了）。
 * 真相源在后端 `complete_lesson` 的日期校验 —— 这里只让老师在点之前就看见。
 */
const isFuture = computed(
  () => !!detail.value && detail.value.lesson_date > todayISO(),
)

/** 未来日期的「已排课」：整块考勤锁住。已完成 / 已取消不受这条影响。 */
const attendanceLocked = computed(
  () => isFuture.value && detail.value?.status === 'scheduled',
)

/** 已取消的课只读 —— 课时都退回去了，再点名没有意义。 */
const editable = computed(
  () =>
    canOperate.value &&
    detail.value?.status !== 'cancelled' &&
    !attendanceLocked.value,
)

/** 这个班是不是「只有出勤才扣」。 */
const onlyPresentCharged = computed(() =>
  PER_STUDENT_HOURS_TYPES.includes(detail.value?.class_type),
)

/**
 * 话术里的班里称呼。**用班型本身**，不要写死「1对1」——
 * 现在 1对2 也走这个分支，写死了就会对着 1对2 的班说「1对1」。
 */
const classLabel = computed(() => detail.value?.class_type || '本班')

/** 上课内容填了才让提交。空着就点，后端会 400 —— 不如先把按钮灰掉。 */
const contentFilled = computed(() => content.value.trim().length > 0)

const contentDirty = computed(
  () => content.value.trim() !== (detail.value?.content || ''),
)

/** 勾选（或上课内容）和已记录的不一样才显示「保存考勤」。 */
const dirty = computed(() => {
  if (!detail.value) return false
  if (contentDirty.value) return true
  return detail.value.students.some(
    (s) => marks.value[s.student_id] !== (s.status || 'present'),
  )
})

// ── 改期审批（2026-10-10）────────────────────────

const APPROVAL_LABELS = {
  pending: '待审批',
  approved: '已通过',
  rejected: '已驳回',
  withdrawn: '已撤回',
}

/** 这节课**最近一条**审批，任何状态（后端 `latest_for_lesson` 按 id 取）。 */
const approval = computed(() => detail.value?.approval || null)

/** 挂着的那条待审批 —— 有它就不能再提，只能撤回。 */
const pendingApproval = computed(() =>
  approval.value?.status === 'pending' ? approval.value : null,
)

/**
 * 老师能不能提改期申请。
 *
 * ⚠️ 管理员**不给这个入口** —— 他改期直接走「编辑」（`PATCH`），
 *    让他给自己发一条审批再自己批是走过场（后端也是 403）。
 */
const canRequestReschedule = computed(
  () => !auth.isAdmin && canOperate.value && detail.value?.status === 'scheduled',
)

const rescheduling = ref(false)
const newDate = ref('')
const newTime = ref('')
const newReason = ref('')

/** 理由必填 —— 它是管理员审批时唯一能看的依据（跟后端一个口径）。 */
const reasonFilled = computed(() => newReason.value.trim().length > 0)

function startReschedule() {
  error.value = ''
  notice.value = ''
  rescheduling.value = true
  // 预填成当前的时间：老师多半只是想挪几天或挪几个钟头，
  // 让他从零填一遍日期是在为难人。
  newDate.value = detail.value.lesson_date
  newTime.value = formatTime(detail.value.start_time)
  newReason.value = ''
}

async function submitReschedule() {
  if (!newDate.value || !newTime.value) {
    error.value = '请选择新的日期和时间'
    return
  }
  if (!reasonFilled.value) {
    error.value = '请填写改期理由（管理员审批时就看它）'
    return
  }

  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    apply(
      await rescheduleLesson(lessonId, {
        date: newDate.value,
        // ⚠️ <input type="time"> 给的是 `HH:MM`，后端要 `HH:MM:SS` —— 补秒。
        //    （`formatTime()` 是反方向的：后端给 `HH:MM:SS`、界面显示 `HH:MM`。）
        start_time: newTime.value.length === 5 ? `${newTime.value}:00` : newTime.value,
        reason: newReason.value.trim(),
      }),
    )
    notice.value = '改期申请已提交，等管理员审批 —— 在那之前课程时间不变'
    rescheduling.value = false
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

async function withdrawReschedule() {
  if (!window.confirm('撤回这条改期申请？撤回后可以重新提交。')) return

  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    // ⚠️ 撤回接口回的是**审批记录**，不是课程详情 —— 不能`apply()` 它的结果，
    //    得重新拉一次课程（`apply` 只认 LessonDetailRead 那个形状）。
    await withdrawApproval(pendingApproval.value.id)
    apply(await getLesson(lessonId))
    notice.value = '已撤回改期申请'
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

/** 这名学生按当前的勾选会不会被扣课时。 */
function willCharge(studentId) {
  if (!onlyPresentCharged.value) return true
  return marks.value[studentId] === 'present'
}

/** 考勤区那句口径说明。两个分支都写清楚，别让老师自己猜。 */
const chargeHint = computed(() => {
  if (!detail.value) return ''
  if (onlyPresentCharged.value) {
    return `${classLabel.value}：只有「出勤」才扣课时，请假和缺勤不扣。`
  }
  // class_type 正常一定有（有课程的班删不掉），兜一下免得显示成「：只要上了课…」
  return (
    `${classLabel.value}：只要上了课，全员都扣课时 ——` +
    '个别学生请假或缺勤照样扣，只有取消课程不扣。'
  )
})

/** 确认框里那句话。按出勤扣的班型要数出勤人数，其他班型直接说全员。 */
function chargeSummary() {
  const hours = detail.value.hours
  const students = detail.value.students

  if (!onlyPresentCharged.value) {
    return `本班 ${students.length} 名学生各扣 ${hours} 课时（请假、缺勤照样扣）。`
  }

  const present = students.filter((s) => willCharge(s.student_id)).length
  const skipped = students.length - present
  return (
    `${classLabel.value}：${present} 名学生出勤，各扣 ${hours} 课时。` +
    (skipped ? `\n请假 / 缺勤的 ${skipped} 名不扣。` : '')
  )
}

function apply(data) {
  detail.value = data
  // 还没点名的课 status 是 null，界面上默认高亮「出勤」
  marks.value = Object.fromEntries(
    data.students.map((s) => [s.student_id, s.status || 'present']),
  )
  content.value = data.content || ''
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    apply(await getLesson(lessonId))
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(load)

function collectItems() {
  return detail.value.students.map((s) => ({
    student_id: s.student_id,
    status: marks.value[s.student_id],
  }))
}

async function run(action, successMessage) {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    apply(await action())
    notice.value = successMessage
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

function finish() {
  if (!contentFilled.value) {
    error.value = '请填写上课内容（这节课上到哪里了）'
    return
  }
  const ok = window.confirm('完成上课并扣课时？\n' + chargeSummary())
  if (!ok) return
  run(
    () => completeLesson(lessonId, content.value.trim(), collectItems()),
    '已完成上课，学生课时已扣除',
  )
}

function saveAttendance() {
  if (!contentFilled.value) {
    error.value = '请填写上课内容（这节课上到哪里了）'
    return
  }
  // 课时会跟着考勤重算（按出勤扣的班型从出勤改成请假就退回去），别说成「课时不变」
  run(
    () => submitAttendance(lessonId, collectItems(), content.value.trim()),
    '考勤已更新，课时已跟着重算',
  )
}

function cancel() {
  const ok = window.confirm(
    '取消这节课？\n' +
      (detail.value.status === 'completed'
        ? '这节课已经扣过课时，取消会把课时退还给每名学生。'
        : '这节课还没上过，没有课时需要退。'),
  )
  if (!ok) return
  run(() => cancelLesson(lessonId), '已取消，课时已退回')
}

async function remove() {
  if (!window.confirm('删除这节课？这是真删，不能恢复。')) return

  busy.value = true
  error.value = ''
  try {
    await deleteLesson(lessonId)
    router.replace({ name: 'lesson-list', query: { date: detail.value.lesson_date } })
  } catch (e) {
    error.value = e.message
    busy.value = false
  }
}

function goBackList() {
  router.push({ name: 'lesson-list', query: { date: detail.value?.lesson_date } })
}
</script>

<template>
  <div class="page page--top page--tabbed">
    <div class="page__inner">
      <AppHeader :title="detail?.class_name || '课程'" to="/lessons">
        <template #actions>
          <button
            v-if="auth.isAdmin && detail?.status === 'scheduled'"
            class="btn btn--sm btn--ghost"
            type="button"
            @click="
              router.push({
                name: 'lesson-edit',
                params: { id: lessonId },
                query: { date: detail.lesson_date },
              })
            "
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
            <strong>{{ detail.lesson_date }} {{ weekdayLabel(detail.lesson_date) }}</strong>
            <span class="tag" :class="STATUS_CLASSES[detail.status]">
              {{ STATUS_LABELS[detail.status] }}
            </span>
          </div>

          <div class="row">
            <span>时间</span>
            <span>{{ formatTime(detail.start_time) }}</span>
          </div>

          <div class="row">
            <span>班级</span>
            <span>{{ detail.class_name }}</span>
          </div>

          <div class="row">
            <span>老师</span>
            <span>{{ detail.teacher_name }}</span>
          </div>

          <div class="row">
            <span>课时</span>
            <span>{{ detail.hours }}</span>
          </div>

          <div class="row">
            <span>费率快照</span>
            <span>¥{{ detail.rate }}/时</span>
          </div>

          <p v-if="detail.note" class="list__meta">{{ detail.note }}</p>
        </div>

        <!-- ★ 改期审批。三个状态各有各的样子：
             没有申请 → 老师能看到「申请改期」入口
             挂着 pending → 显示「待审批 → 新时间」+ 撤回（老师）
             已处理 → 只显示状态（**管理员也看得到**，他得知道这课的时间为什么变过） -->
        <div v-if="approval || canRequestReschedule" class="card">
          <strong>改期申请</strong>

          <template v-if="approval">
            <p class="list__meta">
              {{ APPROVAL_LABELS[approval.status] }} —— 申请改为
              {{ formatDate(approval.new_date) }} {{ formatTime(approval.new_start_time) }}
            </p>

            <p class="lesson__content">理由：{{ approval.reason }}</p>

            <p v-if="approval.reject_reason" class="list__meta">
              驳回理由：{{ approval.reject_reason }}
            </p>

            <p class="list__meta list__meta--quiet">
              {{ approval.requested_by_name }} 提交于
              {{ formatDateTime(approval.requested_at) }}
            </p>

            <p v-if="pendingApproval" class="field__hint">
              管理员通过之前，这节课还在原来的时间上。
            </p>
          </template>

          <!-- 老师：撤回自己提的那条 -->
          <div
            v-if="pendingApproval && canRequestReschedule"
            class="toolbar"
          >
            <button
              class="btn btn--ghost"
              type="button"
              :disabled="busy"
              @click="withdrawReschedule"
            >
              撤回申请
            </button>
          </div>

          <!-- 老师：没有挂着的申请时才给入口（已驳回 / 已撤回的可以重新提） -->
          <template v-if="canRequestReschedule && !pendingApproval">
            <div v-if="!rescheduling" class="toolbar">
              <button
                class="btn btn--ghost"
                type="button"
                :disabled="busy"
                @click="startReschedule"
              >
                申请改期
              </button>
            </div>

            <template v-else>
              <div class="field">
                <label class="field__label" for="reschedule-date">改到哪天</label>
                <input
                  id="reschedule-date"
                  v-model="newDate"
                  class="field__input"
                  type="date"
                />
              </div>

              <div class="field">
                <label class="field__label" for="reschedule-time">几点</label>
                <input
                  id="reschedule-time"
                  v-model="newTime"
                  class="field__input"
                  type="time"
                />
              </div>

              <div class="field">
                <label class="field__label" for="reschedule-reason">
                  改期理由（必填）
                </label>
                <textarea
                  id="reschedule-reason"
                  v-model="newReason"
                  class="field__input field__input--area"
                  rows="2"
                  placeholder="为什么改到那天？管理员审批时只看这一段"
                ></textarea>
              </div>

              <div class="toolbar">
                <button
                  class="btn"
                  type="button"
                  :disabled="busy || !reasonFilled"
                  @click="submitReschedule"
                >
                  提交申请
                </button>
                <button
                  class="btn btn--ghost"
                  type="button"
                  @click="rescheduling = false"
                >
                  取消
                </button>
              </div>
            </template>
          </template>
        </div>

        <!-- 还没到的课：考勤、上课内容整块不给填（后端同样 400）。
             老师可能只是提前点进来看课表，得让他一眼知道**为什么**点不了。 -->
        <p v-if="attendanceLocked" class="hint hint--left">
          还没到上课那天，不能做考勤。要改时间请走上面的「申请改期」（管理员用「编辑」）。
        </p>

        <!-- ★ 上课内容单独一张卡，不塞进信息卡当一行：
             它是「必经的一步」（完成上课必填），视觉上得立得住 -->
        <div v-if="!attendanceLocked" class="card">
          <label class="field__label" for="lesson-content">
            上课内容{{ editable ? '（必填）' : '' }}
          </label>

          <template v-if="editable">
            <textarea
              id="lesson-content"
              v-model="content"
              class="field__input field__input--area"
              rows="3"
              placeholder="这节课上到哪了？例如：第三章 语法复盘 + 练习册 P32"
            ></textarea>
            <p class="field__hint">
              记给以后看的：下节课好接上，家长问起来也有据可查。
            </p>
          </template>

          <p v-else class="content-view">{{ detail.content || '（没有记录）' }}</p>
        </div>

        <p v-if="detail.status === 'cancelled'" class="notice">
          这节课已取消，扣过的课时已经退回给学生。考勤记录保留作为痕迹。
        </p>

        <p class="section">考勤（{{ detail.students.length }} 人）</p>

        <p class="field__hint field__hint--block">{{ chargeHint }}</p>

        <p v-if="!detail.students.length" class="empty">
          上课当天这个班没有在册学生
        </p>

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
              <span class="list__meta">剩 {{ s.remaining_hours }} 课时</span>
            </div>

            <div class="segmented">
              <button
                v-for="option in ATTENDANCE_OPTIONS"
                :key="option.value"
                class="segmented__btn"
                :class="{ 'segmented__btn--on': marks[s.student_id] === option.value }"
                type="button"
                :disabled="!editable || busy"
                @click="marks[s.student_id] = option.value"
              >
                {{ option.label }}
              </button>
            </div>

            <!-- 按当前勾选标出「这人不扣」。按出勤扣的班型改成请假时，
                 老师应该当场看见「不扣」，而不是事后去查流水 -->
            <p v-if="!willCharge(s.student_id)" class="list__meta list__meta--quiet">
              按当前勾选：不扣课时
            </p>
          </div>
        </div>

        <!-- 老师的主流程：勾完点一次，考勤和扣课时一起生效。
             未来的课不给这个按钮 —— 那时还没上，不该能扣课时。 -->
        <div
          v-if="detail.status === 'scheduled' && canOperate && !attendanceLocked"
          class="toolbar"
        >
          <button
            class="btn"
            type="button"
            :disabled="busy || !contentFilled"
            @click="finish"
          >
            {{ contentFilled ? '完成上课（扣课时）' : '先填写上课内容' }}
          </button>
        </div>

        <div v-if="detail.status === 'completed' && canOperate && dirty" class="toolbar">
          <button
            class="btn"
            type="button"
            :disabled="busy || !contentFilled"
            @click="saveAttendance"
          >
            保存考勤
          </button>
        </div>

        <template v-if="auth.isAdmin">
          <div v-if="detail.status !== 'cancelled'" class="toolbar">
            <button class="btn btn--ghost" type="button" :disabled="busy" @click="cancel">
              取消课程
            </button>
          </div>

          <div v-if="detail.status === 'scheduled'" class="toolbar">
            <button class="btn btn--danger" type="button" :disabled="busy" @click="remove">
              删除课程
            </button>
          </div>
        </template>

        <div class="toolbar">
          <button class="btn btn--ghost" type="button" @click="goBackList">
            返回当天课表
          </button>
        </div>
      </template>
    </div>

    <TabBar />
  </div>
</template>

<style scoped>
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

/* 已取消 / 不是自己上的课：上课内容只读展示。
   留 white-space: pre-line —— 老师写内容时可能会换行 */
.content-view {
  margin: 0;
  font-size: 15px;
  white-space: pre-line;
}
</style>
