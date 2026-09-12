<template>
  <div class="layout">
    <aside class="side">
      <div class="logo">
        AIGC 生成平台
        <small>8× V100 · 多模态算力池</small>
      </div>
      <nav>
        <a v-for="m in menus" :key="m.path" :href="'#' + m.path"
           :class="{ 'router-link-active': $route.path === m.path }">
          <span>{{ m.icon }}</span>{{ m.title }}
        </a>
      </nav>
      <div style="padding: 14px 20px; border-top: 1px solid rgba(255,255,255,.08)">
        <div style="font-size: 13px; color: #fff">{{ auth.username }}</div>
        <div style="font-size: 11px; color: #7a8aa0; margin: 4px 0 8px">{{ auth.role }}</div>
        <el-button size="small" type="info" plain @click="logout">退出登录</el-button>
      </div>
    </aside>
    <main class="main">
      <router-view />
    </main>
    <aside class="right">
      <TaskPanel />
    </aside>
  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from '../stores/auth'
import TaskPanel from '../components/TaskPanel.vue'

const auth = useAuthStore()

const menus = [
  { path: '/dashboard', title: '工作台', icon: '🏠' },
  { path: '/text', title: '文生文', icon: '📝' },
  { path: '/image-edit', title: '图生图', icon: '🖼️' },
  { path: '/image-to-video', title: '图生视频', icon: '🎬' },
  { path: '/text-to-video', title: '文生视频', icon: '🎞️' },
  { path: '/assets', title: '素材库', icon: '📁' },
  { path: '/tasks', title: '任务中心', icon: '📋' },
  { path: '/models', title: '模型管理', icon: '🧠' },
  { path: '/monitor', title: '系统监控', icon: '📈' }
]

function logout() {
  auth.logout()
  location.href = '/login'
}
</script>
