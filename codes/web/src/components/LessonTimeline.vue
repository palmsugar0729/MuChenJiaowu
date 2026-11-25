<script setup>
/**
 * 一天的时间轴（课程页日视图的「时间轴」那一档）。
 *
 * 布局：纵轴是时间，一节课一个块，块高按课时数；**时间上有交叠的课左右分栏**，
 * 不交叠的占满整行 —— 所以一个人看自己的课时是一列大块，管理员看全店时
 * 同时段的不同老师会并排。
 *
 * 用户 2026-11-25 定的：块里**两行** —— 第 1 行老师名，第 2 行班级名。
 *
 * ⚠️ 纯展示组件：数据全从 `lessons` 进来，点块只往外抛 `open`。
 *    不在这里请求接口 —— 日视图已经拉过当天全部了，别再拉一遍。
 */
import { computed } from 'vue'

import { formatTime } from '@/utils/date'

const props = defineProps({
  /** `GET /api/lessons?date=` 的返回：管理员是全部老师的课，老师只有自己的 */
  lessons: { type: Array, default: () => [] },
})

const emit = defineEmits(['open'])

/** 一小时的像素高度。块高 = 课时数 × 这个值，所以 1.5 课时就是 90px。 */
const PX_PER_HOUR = 60

/** 课的班型配色有几种（见本文件末尾的 `.tl__block--c0`…`--c5`） */
const PALETTE_SIZE = 6

function minutesOf(hhmmss) {
  const [h, m] = String(hhmmss).split(':').map(Number)
  return (h || 0) * 60 + (m || 0)
}

function startMin(lesson) {
  return minutesOf(lesson.start_time)
}

function endMin(lesson) {
  return startMin(lesson) + Math.max(lesson.hours, 0.25) * 60
}

/** 轴的起止：当天最早一节课所在的小时 ~ 最晚一节课结束所在的小时。 */
const range = computed(() => {
  if (!props.lessons.length) return { from: 8 * 60, to: 20 * 60 }
  const from = Math.floor(Math.min(...props.lessons.map(startMin)) / 60) * 60
  const to = Math.ceil(Math.max(...props.lessons.map(endMin)) / 60) * 60
  return { from, to: Math.max(to, from + 60) } // 至少显示一小时，免得空轴高度为 0
})

const totalHeight = computed(() => ((range.value.to - range.value.from) / 60) * PX_PER_HOUR)

/** 整点的横线和刻度 */
const hourMarks = computed(() => {
  const marks = []
  for (let m = range.value.from; m <= range.value.to; m += 60) {
    marks.push({ top: ((m - range.value.from) / 60) * PX_PER_HOUR, label: `${String(m / 60).padStart(2, '0')}:00` })
  }
  return marks
})

/**
 * 摆块：先按开始时间排序，把**时间上连成一片**的课聚成一组，
 * 组内按「谁先结束谁先腾出位置」贪心分列，组内所有块平分这一组的宽度。
 *
 * ⚠️ 分栏是按**组**算的，不是按全天算 —— 按全天算的话，上午有两节叠在一起的课，
 *    下午单独一节课也会被压成一半宽，看着像排错了。
 */
const blocks = computed(() => {
  const sorted = [...props.lessons].sort(
    (a, b) => startMin(a) - startMin(b) || a.id - b.id,
  )

  // 1. 聚簇
  const clusters = []
  let current = null
  for (const lesson of sorted) {
    const s = startMin(lesson)
    const e = endMin(lesson)
    if (!current || s >= current.end) {
      current = { end: e, items: [lesson] }
      clusters.push(current)
    } else {
      current.items.push(lesson)
      current.end = Math.max(current.end, e)
    }
  }

  // 2. 组内分列 + 算像素位置
  const out = []
  for (const cluster of clusters) {
    const columnEnds = []
    const placed = []
    for (const lesson of cluster.items) {
      const s = startMin(lesson)
      const e = endMin(lesson)
      let col = columnEnds.findIndex((end) => end <= s)
      if (col === -1) {
        col = columnEnds.length
        columnEnds.push(e)
      } else {
        columnEnds[col] = e
      }
      placed.push({ lesson, col })
    }

    const count = columnEnds.length
    for (const { lesson, col } of placed) {
      const height = ((endMin(lesson) - startMin(lesson)) / 60) * PX_PER_HOUR
      out.push({
        lesson,
        style: {
          top: `${((startMin(lesson) - range.value.from) / 60) * PX_PER_HOUR}px`,
          height: `${height}px`,
          left: `${(col / count) * 100}%`,
          width: `${(1 / count) * 100}%`,
        },
        // 太矮的块塞不下第三行时间，只留老师 + 班级
        showTime: height >= 56,
        tone: `tl__block--c${lesson.class_id % PALETTE_SIZE}`,
      })
    }
  }
  return out
})

function timeRange(lesson) {
  return `${formatTime(lesson.start_time)}–${formatTime(lessonStartEnd(lesson))}`
}

/** 结束时间 = 开始 + 课时。后端不存 `end_time`，这里现算。 */
function lessonStartEnd(lesson) {
  const total = Math.round(endMin(lesson))
  const h = Math.floor(total / 60) % 24
  const m = total % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}
</script>

<template>
  <div class="tl" :style="{ height: `${totalHeight}px` }">
    <!-- 整点刻度：绝对定位在轴的最左边那条窄栏里 -->
    <div
      v-for="mark in hourMarks"
      :key="mark.label"
      class="tl__hour"
      :style="{ top: `${mark.top}px` }"
    >
      <span class="tl__hour-label">{{ mark.label }}</span>
    </div>

    <!-- 块单独放一层：百分比宽度按这一层的宽度算，才不会被左边 44px 的刻度栏带歪 -->
    <div class="tl__track">
      <button
        v-for="block in blocks"
        :key="block.lesson.id"
        class="tl__block"
        :class="[block.tone, { 'tl__block--cancelled': block.lesson.status === 'cancelled' }]"
        :style="block.style"
        type="button"
        @click="emit('open', block.lesson)"
      >
        <span class="tl__teacher">{{ block.lesson.teacher_name }}</span>
        <span class="tl__class">{{ block.lesson.class_name }}</span>
        <span v-if="block.showTime" class="tl__time">{{ timeRange(block.lesson) }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
/* 左边留一条窄栏放整点刻度，右边的块都从这条栏之后开始 */
.tl {
  position: relative;
  margin-top: 16px;
  padding-left: 44px;
}

.tl__hour {
  position: absolute;
  left: 0;
  right: 0;
  height: 0;
  border-top: 1px solid var(--color-border);
}

.tl__hour-label {
  position: absolute;
  top: -9px;
  left: 0;
  /* 刻度压在横线上，得给它一层底遮住线，否则「08:00」会被划一道 */
  padding-right: 4px;
  background: var(--color-page);
  font-size: 11px;
  color: var(--color-text-muted);
  font-variant-numeric: tabular-nums;
}

/* 块的定位层。单独一层是为了让块上的百分比宽度按「刻度栏右边那块」算 */
.tl__track {
  position: relative;
  height: 100%;
}

/* 块：绝对定位，位置和高度全由 JS 算好塞进 :style */
.tl__block {
  position: absolute;
  display: flex;
  flex-direction: column;
  gap: 1px;
  overflow: hidden;
  padding: 6px 8px;
  border: none;
  border-left: 3px solid transparent;
  border-radius: var(--radius-sm);
  text-align: left;
  cursor: pointer;
  box-sizing: border-box;
  /* 右边留 2px 透明边 + 背景只画到 padding 区 —— 并排两栏之间就有了一道缝 */
  border-right: 2px solid transparent;
  background-clip: padding-box;
}

.tl__teacher {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tl__class {
  font-size: 12px;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tl__time {
  font-size: 11px;
  color: var(--color-text-muted);
  font-variant-numeric: tabular-nums;
}

/* 已取消的课留着但灰掉 —— 让它凭空消失比灰着更难懂 */
.tl__block--cancelled {
  opacity: 0.5;
  border-left-style: dashed;
}

/* 按 class_id 取色，同一个班永远同一个颜色 */
.tl__block--c0 { background: #e3efe6; border-left-color: #8fb9a0; }
.tl__block--c1 { background: #e6ecf7; border-left-color: #93a9d8; }
.tl__block--c2 { background: #f7ecdf; border-left-color: #d8ab7c; }
.tl__block--c3 { background: #f1e6f2; border-left-color: #b28fbb; }
.tl__block--c4 { background: #f2f0dd; border-left-color: #bfb96f; }
.tl__block--c5 { background: #e2f0f0; border-left-color: #82b3b3; }
</style>
