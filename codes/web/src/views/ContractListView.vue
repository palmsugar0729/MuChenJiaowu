<script setup>
/**
 * 合同管理 —— **占位页**。
 *
 * 用户 2026-10-05 要的只是「先有个入口，里面暂时什么都不要放」。
 * 所以这里没有接口、没有表格、没有状态，只有一个空态说明。
 *
 * ⚠️ 别顺手在这里加东西。真要做的时候，先定合同的数据模型
 *    （跟学生怎么关联、跟课时/金额什么关系、要不要附件），再动这个页面。
 *    现在放任何「猜的」字段，将来都要重写。
 *
 * 权限：**只给管理员**。底栏不给老师显示这个 tab，router 的守卫也会拦手输 URL。
 */

import AppHeader from '@/components/AppHeader.vue'
import TabBar from '@/components/TabBar.vue'
</script>

<template>
  <div class="page page--top page--tabbed">
    <div class="page__inner">
      <!-- 一级页面，没有「上一页」可退 -->
      <AppHeader title="合同" :back="false" />

      <p class="empty">合同管理还没做，先留个入口</p>

      <p class="hint">
        以后放报名合同、课时包、缴费记录这些东西。现在还没有设计，所以是空的。
      </p>
    </div>

    <TabBar />
  </div>
</template>
