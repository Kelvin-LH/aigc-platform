import type { AssetOut, ModelOut, TaskEvent, TaskOut } from './types'

const BASE = '/api/v1'

function headers(auth = true): Record<string, string> {
  const h: Record<string, string> = { 'Content-Type': 'application/json' }
  if (auth) {
    const token = localStorage.getItem('token')
    if (token) h.Authorization = `Bearer ${token}`
  }
  return h
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method,
    headers: headers(),
    body: body === undefined ? undefined : JSON.stringify(body)
  })
  if (res.status === 401) {
    localStorage.removeItem('token')
    location.href = '/login'
    throw new Error('未登录')
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail))
  }
  return res.json()
}

export const api = {
  login: (username: string, password: string) =>
    request<{ access_token: string }>('POST', '/auth/login', { username, password }),

  listTasks: (status?: string) =>
    request<TaskOut[]>('GET', `/tasks${status ? `?status=${status}` : ''}`),
  getTask: (id: string) => request<TaskOut>('GET', `/tasks/${id}`),
  getTaskDetail: (id: string) => request<any>('GET', `/tasks/${id}/detail`),
  cancelTask: (id: string) => request<TaskOut>('POST', `/tasks/${id}/cancel`),
  retryTask: (id: string) => request<TaskOut>('POST', `/tasks/${id}/retry`),

  submitTask: (endpoint: string, body: Record<string, unknown>) =>
    request<TaskOut>('POST', `/generate/${endpoint}`, body),

  listAssets: (type?: string) =>
    request<AssetOut[]>('GET', `/assets${type ? `?type=${type}` : ''}`),
  uploadAsset: async (file: File, projectId?: number): Promise<AssetOut> => {
    const fd = new FormData()
    fd.append('file', file)
    if (projectId) fd.append('project_id', String(projectId))
    const res = await fetch(`${BASE}/assets`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${localStorage.getItem('token') ?? ''}` },
      body: fd
    })
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? '上传失败')
    return res.json()
  },

  listModels: () => request<ModelOut[]>('GET', '/models'),
  gpuStatus: () => request<any>('GET', '/monitor/gpus'),
  queueStatus: () => request<any>('GET', '/monitor/queue'),
  overview: () => request<any>('GET', '/monitor/overview')
}

/** 订阅任务 SSE 进度事件 */
export function subscribeTaskEvents(
  taskId: string,
  onEvent: (e: TaskEvent) => void,
  onDone?: () => void
): EventSource {
  const es = new EventSource(`${BASE}/tasks/${taskId}/events`)
  es.onmessage = (msg) => {
    try {
      onEvent(JSON.parse(msg.data))
    } catch { /* ignore */ }
  }
  es.onerror = () => { onDone?.() }
  return es
}
