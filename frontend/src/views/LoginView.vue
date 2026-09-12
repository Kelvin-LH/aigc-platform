<template>
  <div style="height: 100vh; display: flex; align-items: center; justify-content: center; background: #1d2530">
    <el-card style="width: 380px">
      <h2 style="margin: 0 0 6px; text-align: center">AIGC 多模态生成平台</h2>
      <p class="muted" style="text-align: center; margin: 0 0 18px">统一入口 · 异步任务 · 8×V100 算力池</p>
      <el-form @submit.prevent="doLogin">
        <el-form-item>
          <el-input v-model="username" placeholder="用户名" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="password" type="password" placeholder="密码" show-password />
        </el-form-item>
        <el-button type="primary" style="width: 100%" :loading="loading" native-type="submit">
          登 录
        </el-button>
      </el-form>
      <p class="muted" style="margin-top: 12px; text-align: center">
        默认管理员 admin / admin123 · 演示账号 creator / creator123
      </p>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import { useAuthStore } from '../stores/auth'

const username = ref('admin')
const password = ref('admin123')
const loading = ref(false)
const router = useRouter()
const auth = useAuthStore()

async function doLogin() {
  loading.value = true
  try {
    const res = await api.login(username.value, password.value)
    auth.setToken(res.access_token)
    router.push('/dashboard')
  } catch (e: any) {
    ElMessage.error(e.message ?? '登录失败')
  } finally {
    loading.value = false
  }
}
</script>
