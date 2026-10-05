<script setup>
/**
 * 班级表单 —— 新建和编辑复用同一个组件，靠路由里有没有 `id` 区分。
 *
 * 这页的重点是**班级名 → 班级类型 → 费率**的三级联动：
 *   YDY001 一敲，类型就锁成「1对1」、费率自动填 80，用户不用记这张表。
 *
 * ⚠️ 这里的联动只是**即时反馈**。真相源在后端（core/class_rules.py），
 *    提交时它还会独立校验一遍。所以就算前端算错了，也不会写进脏数据 ——
 *    只是会吃一个 400，把后端的原话显示出来就行。
 */

import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { createClass, getClass, updateClass } from '@/api/classes'
import AppHeader from '@/components/AppHeader.vue'
import { useMetaStore } from '@/stores/meta'

const meta = useMetaStore()
const route = useRoute()
const router = useRouter()

const classId = route.params.id ? Number(route.params.id) : null
const isEdit = classId !== null

const form = ref({ name: '', class_type: '', rate: '', note: '' })
const hasLessons = ref(false)
const loading = ref(true)
const saving = ref(false)
const error = ref('')

/** 用户有没有手动改过费率 —— 改过就不再被联动覆盖掉 */
const rateTouched = ref(false)

const rule = computed(() => meta.classTypeRule(form.value.name))

/** 类型能不能改：YDY/YDE 被前缀锁死，其余可选 */
const typeLocked = computed(() => rule.value.mode === 'fixed')

const typeOptions = computed(() => {
  const base = rule.value.options
  const current = form.value.class_type

  // 存量数据里可能有费率表之外的类型（历史命名，后端对「认不出前缀」的班是允许的）。
  // 把当前值补进选项里，否则下面的 watch 会把它当成「不在选项里」清掉 ——
  // 前端不认识 ≠ 这个值是错的，不能顺手把人家数据抹了。
  return current && !base.includes(current) ? [...base, current] : base
})

onMounted(async () => {
  try {
    // 规则表是前端联动的依据，进这一页必须拿到，拿不到就只能靠后端兜底
    await meta.load()

    if (isEdit) {
      const detail = await getClass(classId)
      form.value = {
        name: detail.name,
        class_type: detail.class_type,
        rate: String(detail.rate),
        note: detail.note || '',
      }
      hasLessons.value = detail.has_lessons
      // 编辑时把已有费率当作「用户已经定过」，别一进来就被联动改掉
      rateTouched.value = true
    }
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

/**
 * 班级名一变就重算类型。
 *
 * `fixed`（YDY/YDE）→ 直接锁定并选中；
 * `small`（XB）→ 给选项但**不预选**，逼用户自己挑（后端对 XB 要求显式指定）；
 * `free` → 全部类型可选，也不预选。
 *
 * 已经选过的类型如果还在新选项里，就留着 —— 不然用户改个错字，
 * 刚选好的东西会被清掉。
 */
watch(
  () => form.value.name,
  () => {
    if (!meta.loaded) return

    if (rule.value.mode === 'fixed') {
      form.value.class_type = rule.value.default
      return
    }

    if (!typeOptions.value.includes(form.value.class_type)) {
      form.value.class_type = ''
    }
  },
)

/** 类型变了就带出建议费率；用户手动改过就不再覆盖。 */
watch(
  () => form.value.class_type,
  (type) => {
    if (rateTouched.value || !type) return
    const suggested = meta.rateFor(type)
    if (suggested !== null) form.value.rate = String(suggested)
  },
)

function onRateInput() {
  rateTouched.value = true
}

/** 用户把费率清空 → 交回给联动管，下次选类型时重新带默认值 */
function onRateBlur() {
  if (!form.value.rate) rateTouched.value = false
}

async function submit() {
  error.value = ''

  if (!form.value.name.trim()) {
    error.value = '请填写班级名'
    return
  }
  if (!form.value.class_type) {
    error.value = '请选择班级类型'
    return
  }

  // 费率可留空 —— 后端会按类型补默认值。填了就必须是正数。
  const rate = form.value.rate === '' ? null : Number(form.value.rate)
  if (rate !== null && (!Number.isFinite(rate) || rate <= 0)) {
    error.value = '费率必须大于 0'
    return
  }

  const payload = {
    name: form.value.name.trim(),
    class_type: form.value.class_type,
    note: form.value.note.trim(),
  }
  if (rate !== null) payload.rate = rate

  saving.value = true
  try {
    const saved = isEdit
      ? await updateClass(classId, payload)
      : await createClass(payload)
    router.replace({ name: 'class-detail', params: { id: saved.id } })
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
        :title="isEdit ? '编辑班级' : '新建班级'"
        :to="isEdit ? `/classes/${classId}` : '/classes'"
      />

      <p v-if="error" class="alert">{{ error }}</p>
      <p v-if="loading" class="hint">加载中…</p>

      <form v-else class="card" @submit.prevent="submit">
        <div class="field">
          <label class="field__label" for="name">班级名</label>
          <input
            id="name"
            v-model="form.name"
            class="field__input"
            type="text"
            placeholder="例如 YDY001"
          />
          <p class="field__hint">
            以 YDY 开头自动定为 1对1，YDE 是 1对2，XB 开头需要自己选人数。
          </p>
        </div>

        <div class="field">
          <label class="field__label" for="type">班级类型</label>
          <select
            id="type"
            v-model="form.class_type"
            class="field__select"
            :disabled="typeLocked"
          >
            <option value="" disabled>请选择</option>
            <option v-for="type in typeOptions" :key="type" :value="type">
              {{ type }}
            </option>
          </select>
          <p v-if="typeLocked" class="field__hint">
            由班级名前缀决定，不能改。
          </p>
        </div>

        <div class="field">
          <label class="field__label" for="rate">费率（元/课时）</label>
          <input
            id="rate"
            v-model="form.rate"
            class="field__input"
            type="number"
            inputmode="decimal"
            min="0"
            step="0.5"
            placeholder="留空按班级类型自动填"
            @input="onRateInput"
            @blur="onRateBlur"
          />
          <p class="field__hint">
            <template v-if="hasLessons">
              ⚠️ 改费率不会影响已经排过的课 —— 每节课的费率在排课时就抄下来了，
              改价只影响以后新排的课。
            </template>
            <template v-else> 留空就按班级类型的默认价填。 </template>
          </p>
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

        <button class="btn" type="submit" :disabled="saving">
          {{ saving ? '保存中…' : '保存' }}
        </button>
      </form>
    </div>
  </div>
</template>
