import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/login', component: () => import('../views/LoginView.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('../views/LayoutView.vue'),
    redirect: '/dashboard',
    children: [
      { path: 'dashboard', component: () => import('../views/DashboardView.vue'), meta: { title: '工作台' } },
      { path: 'text', component: () => import('../views/TextGenView.vue'), meta: { title: '文生文' } },
      { path: 'image-edit', component: () => import('../views/ImageEditView.vue'), meta: { title: '图生图' } },
      { path: 'image-to-video', component: () => import('../views/ImageToVideoView.vue'), meta: { title: '图生视频' } },
      { path: 'text-to-video', component: () => import('../views/TextToVideoView.vue'), meta: { title: '文生视频' } },
      { path: 'assets', component: () => import('../views/AssetsView.vue'), meta: { title: '素材库' } },
      { path: 'tasks', component: () => import('../views/TasksView.vue'), meta: { title: '任务中心' } },
      { path: 'models', component: () => import('../views/ModelsView.vue'), meta: { title: '模型管理' } },
      { path: 'monitor', component: () => import('../views/MonitorView.vue'), meta: { title: '系统监控' } }
    ]
  }
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to) => {
  if (!to.meta.public && !localStorage.getItem('token')) return '/login'
})

export default router
