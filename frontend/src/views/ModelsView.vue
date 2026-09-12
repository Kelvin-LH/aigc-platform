<template>
  <h1 class="page-title">模型管理</h1>
  <div class="card">
    <p class="muted" style="margin-top: 0">
      一个业务能力可挂多个后端；前端只展示“快速/标准/高质量”档位，底层 checkpoint 在此切换。
      V100（Volta）生产模型默认 FP16，禁止 FP8/Hopper 专用算子。
    </p>
    <el-table :data="models" size="default">
      <el-table-column prop="capability" label="能力" width="120" />
      <el-table-column prop="name" label="模型" min-width="180" />
      <el-table-column prop="quality_tier" label="质量档位" width="100" />
      <el-table-column label="资源档位" width="110">
        <template #default="{ row }">{{ PROFILE_LABELS[row.resource_profile] ?? row.resource_profile }}</template>
      </el-table-column>
      <el-table-column prop="dtype" label="dtype" width="80" />
      <el-table-column label="CPU Offload" width="110">
        <template #default="{ row }">{{ row.supports_cpu_offload ? '支持' : '—' }}</template>
      </el-table-column>
      <el-table-column prop="license" label="License" min-width="160" />
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? '启用' : '停用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="110">
        <template #default="{ row }">
          <el-button size="small" link :type="row.enabled ? 'danger' : 'primary'" @click="toggle(row)">
            {{ row.enabled ? '停用' : '启用' }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'
import { PROFILE_LABELS, type ModelOut } from '../api/types'

const models = ref<ModelOut[]>([])

async function refresh() { try { models.value = await api.listModels() } catch { /* ignore */ } }
async function toggle(m: ModelOut) {
  try { await fetch(`/api/v1/models/${m.id}/enabled`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('token')}` },
    body: JSON.stringify({ enabled: !m.enabled })
  }); refresh() } catch (e: any) { ElMessage.error(e.message) }
}
onMounted(refresh)
</script>
