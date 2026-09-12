<template>
  <h1 class="page-title">任务中心</h1>
  <div class="card">
    <div style="display: flex; gap: 10px; margin-bottom: 12px">
      <el-select v-model="filterStatus" placeholder="全部状态" clearable style="width: 160px" @change="refresh">
        <el-option v-for="(label, key) in STATUS_LABELS" :key="key" :label="label" :value="key" />
      </el-select>
      <el-button @click="refresh">刷新</el-button>
    </div>
    <el-table :data="tasks" size="default">
      <el-table-column label="任务 ID" width="110">
        <template #default="{ row }"><span class="muted">{{ row.id.slice(0, 8) }}…</span></template>
      </el-table-column>
      <el-table-column label="类型" width="120">
        <template #default="{ row }">{{ TASK_TYPE_LABELS[row.task_type] ?? row.task_type }}</template>
      </el-table-column>
      <el-table-column label="模型" min-width="160" prop="model_key" />
      <el-table-column label="档位" width="110">
        <template #default="{ row }">{{ PROFILE_LABELS[row.resource_profile] ?? row.resource_profile }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag size="small" :type="(STATUS_TYPES[row.status] as any) ?? 'info'">
            {{ STATUS_LABELS[row.status] ?? row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="进度" width="170">
        <template #default="{ row }">
          <el-progress :percentage="row.progress" :stroke-width="8" />
          <div class="muted">{{ row.stage }}</div>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150">
        <template #default="{ row }">
          <el-button v-if="cancellable(row.status)" size="small" link type="danger" @click="cancel(row)">取消</el-button>
          <el-button v-if="['FAILED', 'CANCELED'].includes(row.status)" size="small" link type="primary"
                     @click="retry(row)">重试</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'
import { PROFILE_LABELS, STATUS_LABELS, STATUS_TYPES, TASK_TYPE_LABELS, type TaskOut } from '../api/types'

const tasks = ref<TaskOut[]>([])
const filterStatus = ref('')
let timer: number | undefined

const cancellable = (s: string) => !['SUCCEEDED', 'FAILED', 'CANCELED'].includes(s)

async function refresh() {
  try { tasks.value = await api.listTasks(filterStatus.value || undefined) } catch { /* 静默 */ }
}
async function cancel(t: TaskOut) {
  try { await api.cancelTask(t.id); ElMessage.success('已请求取消'); refresh() } catch (e: any) { ElMessage.error(e.message) }
}
async function retry(t: TaskOut) {
  try { await api.retryTask(t.id); ElMessage.success('已重新提交'); refresh() } catch (e: any) { ElMessage.error(e.message) }
}
onMounted(() => { refresh(); timer = window.setInterval(refresh, 4000) })
onBeforeUnmount(() => window.clearInterval(timer))
</script>
