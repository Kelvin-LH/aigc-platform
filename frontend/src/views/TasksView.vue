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
      <el-table-column label="操作" width="190">
        <template #default="{ row }">
          <el-button size="small" link type="primary" @click="showDetail(row)">查看</el-button>
          <el-button v-if="cancellable(row.status)" size="small" link type="danger" @click="cancel(row)">取消</el-button>
          <el-button v-if="['FAILED', 'CANCELED'].includes(row.status)" size="small" link type="primary"
                     @click="retry(row)">重试</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>

  <!-- 任务详情弹窗 -->
  <el-dialog v-model="detailVisible" :title="`任务详情 ${detailTask?.id?.slice(0, 8) ?? ''}…`" width="720px">
    <template v-if="detail">
      <el-descriptions :column="2" border size="small" style="margin-bottom: 14px">
        <el-descriptions-item label="类型">{{ TASK_TYPE_LABELS[detailTask?.task_type ?? ''] }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag size="small" :type="(STATUS_TYPES[detailTask?.status ?? ''] as any) ?? 'info'">
            {{ STATUS_LABELS[detailTask?.status ?? ''] }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="模型">{{ detailTask?.model_key }}</el-descriptions-item>
        <el-descriptions-item label="GPU">{{ detailTask?.gpu_ids || '—' }}</el-descriptions-item>
      </el-descriptions>
      <h4 style="margin: 0 0 6px">Prompt</h4>
      <p style="background: #f7f8fa; padding: 10px; border-radius: 6px; white-space: pre-wrap">{{ detail.input.prompt || '（无）' }}</p>
      <h4 style="margin: 14px 0 6px">生成结果</h4>
      <div v-if="!detail.outputs.length" class="muted">无输出</div>
      <div v-for="o in detail.outputs" :key="o.id" style="margin-bottom: 12px">
        <img v-if="o.uri?.match(/\.(png|jpe?g|webp)$/i)" :src="o.uri"
             style="max-width: 100%; max-height: 400px; border-radius: 8px" alt="生成图片" />
        <pre v-else-if="detailText && o.uri?.endsWith('.txt')"
             style="white-space: pre-wrap; background: #f7f8fa; padding: 12px; border-radius: 8px; margin: 0">{{ detailText }}</pre>
        <div class="muted">seed: {{ o.seed ?? '—' }} · 模型版本: {{ o.model_version }} · 耗时 {{ (o.runtime_ms / 1000).toFixed(1) }}s</div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'
import { PROFILE_LABELS, STATUS_LABELS, STATUS_TYPES, TASK_TYPE_LABELS, type TaskOut } from '../api/types'

const tasks = ref<TaskOut[]>([])
const filterStatus = ref('')
const detailVisible = ref(false)
const detailTask = ref<TaskOut | null>(null)
const detail = ref<any>(null)
const detailText = ref('')
let timer: number | undefined

async function showDetail(t: TaskOut) {
  detailTask.value = t
  detail.value = null
  detailText.value = ''
  detailVisible.value = true
  try {
    const d: any = await api.getTaskDetail(t.id)
    detail.value = d
    const first = d.outputs?.[0]
    if (first?.uri?.endsWith('.txt')) {
      detailText.value = await (await fetch(first.uri)).text()
    }
  } catch { /* ignore */ }
}

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
