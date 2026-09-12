<template>
  <h1 class="page-title">工作台</h1>
  <div class="stat-grid" style="margin-bottom: 16px">
    <div class="stat"><div class="num">{{ data.gpus?.free?.length ?? '-' }} / {{ data.gpus?.total ?? 8 }}</div>
      <div class="muted">空闲 GPU（V100）</div></div>
    <div class="stat"><div class="num">{{ data.queue?.SUCCEEDED ?? 0 }}</div><div class="muted">已完成任务</div></div>
    <div class="stat"><div class="num">{{ data.queue?.RUNNING ?? 0 }}</div><div class="muted">运行中任务</div></div>
    <div class="stat"><div class="num">{{ data.queue?.QUEUED ?? 0 }}</div><div class="muted">排队中任务</div></div>
  </div>

  <div class="card">
    <h3>GPU 资源池（gang scheduling：S=1卡 / M=2卡 / L=4卡 / XL=8卡）</h3>
    <div class="gpu-grid">
      <div v-for="i in 8" :key="i" class="gpu-cell" :class="{ busy: !data.gpus?.free?.includes(i - 1) }">
        GPU{{ i - 1 }}<br />{{ data.gpus?.free?.includes(i - 1) ? '空闲' : '占用' }}
      </div>
    </div>
  </div>

  <div class="card">
    <h3>最近任务</h3>
    <el-table :data="data.recent_tasks ?? []" size="small">
      <el-table-column prop="type" label="类型" width="160" />
      <el-table-column prop="status" label="状态" width="110" />
      <el-table-column prop="stage" label="阶段" min-width="200" />
      <el-table-column prop="created_at" label="创建时间" width="180" />
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '../api/client'

const data = ref<any>({})
let timer: number | undefined

async function refresh() { try { data.value = await api.overview() } catch { /* 静默 */ } }
onMounted(() => { refresh(); timer = window.setInterval(refresh, 5000) })
onBeforeUnmount(() => window.clearInterval(timer))
</script>
