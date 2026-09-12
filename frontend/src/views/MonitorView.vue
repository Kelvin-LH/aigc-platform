<template>
  <h1 class="page-title">系统监控</h1>
  <div class="card">
    <h3>GPU 状态（8× V100 16GB SXM2 / NVLink）</h3>
    <div class="gpu-grid">
      <div v-for="i in gpus.total || 8" :key="i" class="gpu-cell" :class="{ busy: busy(i - 1) }">
        GPU{{ i - 1 }}<br />{{ busy(i - 1) ? '占用中' : '空闲' }}
      </div>
    </div>
    <p class="muted" style="margin-bottom: 0">{{ gpus.note }}</p>
  </div>
  <div class="card">
    <h3>任务队列统计</h3>
    <el-descriptions :column="5" border size="small">
      <el-descriptions-item v-for="(v, k) in queue.tasks || {}" :key="k" :label="k">{{ v }}</el-descriptions-item>
    </el-descriptions>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '../api/client'

const gpus = ref<any>({})
const queue = ref<any>({})
let timer: number | undefined

const busy = (i: number) => !(gpus.value.free ?? []).includes(i)
async function refresh() {
  try {
    gpus.value = await api.gpuStatus()
    queue.value = await api.queueStatus()
  } catch { /* 静默 */ }
}
onMounted(() => { refresh(); timer = window.setInterval(refresh, 4000) })
onBeforeUnmount(() => window.clearInterval(timer))
</script>
