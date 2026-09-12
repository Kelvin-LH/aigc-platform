<template>
  <h1 class="page-title">素材库</h1>
  <div class="card">
    <div style="display: flex; gap: 10px; margin-bottom: 14px">
      <el-upload :auto-upload="false" :show-file-list="false" :on-change="upload">
        <el-button type="primary">上传素材</el-button>
      </el-upload>
      <el-select v-model="filterType" placeholder="全部类型" clearable style="width: 140px" @change="refresh">
        <el-option label="图片" value="image" /><el-option label="视频" value="video" /><el-option label="文本" value="text" />
      </el-select>
      <el-button @click="refresh">刷新</el-button>
    </div>
    <el-table :data="assets" size="default">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="filename" label="文件名" min-width="200" />
      <el-table-column prop="type" label="类型" width="90" />
      <el-table-column label="大小" width="110">
        <template #default="{ row }">{{ (row.size_bytes / 1024).toFixed(1) }} KB</template>
      </el-table-column>
      <el-table-column prop="sha256" label="SHA256（可追溯）" width="140">
        <template #default="{ row }"><span class="muted">{{ row.sha256.slice(0, 12) }}…</span></template>
      </el-table-column>
      <el-table-column label="操作" width="90">
        <template #default="{ row }">
          <el-button size="small" link type="danger" @click="del(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'
import type { AssetOut } from '../api/types'

const assets = ref<AssetOut[]>([])
const filterType = ref('')

async function refresh() { try { assets.value = await api.listAssets(filterType.value || undefined) } catch { /* ignore */ } }
async function upload(file: any) {
  try { await api.uploadAsset(file.raw); ElMessage.success('上传成功'); refresh() } catch (e: any) { ElMessage.error(e.message) }
}
async function del(a: AssetOut) {
  try { await fetch(`/api/v1/assets/${a.id}`, { method: 'DELETE', headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } }); refresh() } catch { /* ignore */ }
}
onMounted(refresh)
</script>
