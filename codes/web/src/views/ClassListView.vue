<script setup>
/**
 * 班级列表 + 顶部分类卡（总览 / 1对1 / 1对2 / 小班）。
 *
 * ★ 卡面上是**人话**，不是 YDY / YDE / XB 这种内部编码 —— 老师看不懂编码，
 *   用户 2026-10-07 明确提的。卡片本身从后端规则来（`stores/meta.js` 的
 *   classTabs），以后加一档自动多一张卡。
 *
 * ⚠️ **按 `class_type` 筛，不按班级名前缀筛**。历史遗留的自定义班名
 *    （「沐晨提高班」这种）没有前缀，按前缀筛就会切到「1对1」后凭空消失。
 *
 * 选中的分类放在 **URL 的 query 里**（`/classes?tab=xb`），跟课程日视图
 * 一个道理：进班级详情再返回，还停在原来那张卡上，链接也能直接发人。
 */

import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { listClasses } from '@/api/classes'
import AppHeader from '@/components/AppHeader.vue'
import TabBar from '@/components/TabBar.vue'
import { useAuthStore } from '@/stores/auth'
import { useMetaStore } from '@/stores/meta'

const auth = useAuthStore()
const meta = useMetaStore()
const route = useRoute()
const router = useRouter()

/**
 * 「总览」是唯一一张前端自己加的卡：它不属于任何 class_type，`types` 为 null
 * = 不筛。其余卡片一律由后端给（`meta.classTabs`）。
 */
const ALL = { key: 'all', label: '总览', types: null }

const classes = ref([])
const showInactive = ref(false)
const loading = ref(true)
const error = ref('')

const tabs = computed(() => [ALL, ...meta.classTabs])

/** 当前选中的分类。认不出的值一律当「总览」，免得手改 URL 出现空列表 */
const activeTab = computed(() => {
  const wanted = route.query.tab
  return tabs.value.find((tab) => tab.key === wanted) || ALL
})

/**
 * 分类是**前端过滤**，不再跑一趟接口 —— 班级总数几十个，犯不上。
 *
 * ⚠️ 比的是 `class_type`（可能命中多个，小班那张卡是 1对3/1对4/1对5 合起来的），
 *    不是班级名前缀。
 */
const visibleClasses = computed(() => {
  const types = activeTab.value.types
  if (!types) return classes.value
  return classes.value.filter((klass) => types.includes(klass.class_type))
})

/**
 * 在册人数 / 上限。上限认不出来（自定义类型）时只显示人数。
 * ⚠️ 超员是**真实存在过的历史数据**（改规则之前建的班），所以这里要能看出来，
 *    不然用户只会觉得「为什么加不进去了」。
 */
function occupancy(klass) {
  const cap = meta.capacityFor(klass.class_type)
  return cap === null
    ? `在册 ${klass.student_count} 人`
    : `在册 ${klass.student_count}/${cap} 人`
}

function isOverCapacity(klass) {
  const cap = meta.capacityFor(klass.class_type)
  return cap !== null && klass.student_count > cap
}

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

onMounted(async () => {
  // 分类卡要先拿到前缀规则。拿不到就退化成只有「总览」，不影响看列表。
  try {
    await meta.load()
  } catch {
    // 故意吞掉：班级列表本身还能用
  }
  await load()
})

watch(showInactive, load)

function selectTab(tab) {
  router.replace({
    name: 'class-list',
    // 「总览」不带 query，让地址栏干净（`/classes` 而不是 `/classes?tab=all`）
    query: tab.key === ALL.key ? {} : { tab: tab.key },
  })
}
</script>

<template>
  <div class="page page--top">
    <div class="page__inner">
      <!-- 一级页面，没有「上一页」可退 -->
      <AppHeader title="班级" :back="false">
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

      <div class="segmented">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="segmented__btn"
          :class="{ 'segmented__btn--on': activeTab.key === tab.key }"
          type="button"
          @click="selectTab(tab)"
        >
          {{ tab.label }}
        </button>
      </div>

      <label class="checkbox">
        <input v-model="showInactive" type="checkbox" />
        <span>显示已停用</span>
      </label>

      <p v-if="loading" class="hint">加载中…</p>

      <p v-else-if="!visibleClasses.length" class="empty">
        {{ activeTab.types ? `还没有「${activeTab.label}」的班级` : '还没有班级' }}
      </p>

      <div v-else class="list">
        <button
          v-for="klass in visibleClasses"
          :key="klass.id"
          class="list__item"
          type="button"
          @click="router.push({ name: 'class-detail', params: { id: klass.id } })"
        >
          <div class="row">
            <p class="list__title">{{ klass.name }}</p>
            <span v-if="!klass.is_active" class="tag tag--muted">已停用</span>
            <span v-else-if="isOverCapacity(klass)" class="tag tag--warn">超员</span>
          </div>
          <p class="list__meta">
            <span class="tag">{{ klass.class_type }}</span>
            ¥{{ klass.rate }}/课时 · {{ occupancy(klass) }}
          </p>
        </button>
      </div>
    </div>

    <TabBar />
  </div>
</template>
