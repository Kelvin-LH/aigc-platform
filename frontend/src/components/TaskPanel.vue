<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '../api/client'
import { PROFILE_LABELS, STATUS_LABELS, STATUS_TYPES, TASK_TYPE_LABELS, type TaskOut } from '../api/types'

const tasks = ref<TaskOut[]>([])
let timer: number | undefined

async function refresh() {
  try {
    tasks.value = await api.listTasks()
  } catch { /* 静默轮询 */ }
}

onMounted(() => {
  refresh()
  timer = window.setInterval(refresh, 4000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <h3 style="margin: 4px 0 10px; font-size: 14px">任务队列</h3>
  <div v-if="!tasks.length" class="muted">暂无任务</div>
  <div v-for="t in tasks.slice(0, 20)" :key="t.id" class="task-mini"
       style="padding: 8px 0; border-bottom: 1px solid #f0f2f5; font-size: 12px">
    <div style="display: flex; justify-content: space-between; align-items: center">
      <b style="color: #303133">{{ TASK_TYPE_LABELS[t.task_type] ?? t.task_type }}</b>
      <el-tag size="small" :type="(STATUS_TYPES[t.status] as any) ?? 'info'">
        {{ STATUS_LABELS[t.status] ?? t.status }}
      </el-tag>
    </div>
    <div class="muted" style="margin: 3px 0">
      {{ t.model_key }} · {{ PROFILE_LABELS[t.resource_profile] ?? t.resource_profile }}
      <span v-if="t.gpu_ids"> · GPU {{ t.gpu_ids }}</span>
    </div>
    <el-progress v-if="t.status !== 'SUCCEEDED' && t.status !== 'FAILED'" :percentage="t.progress" :stroke-width="4" />
    <div v-else-if="t.status === 'FAILED'" style="color: #d9534f">{{ t.error_code }}</div>
  </div>
</template>
